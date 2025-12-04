package com.ccd.monitoring_service.service;

import com.ccd.monitoring_service.dto.LogMessageDto;
import com.ccd.monitoring_service.dto.LogType;
import com.ccd.monitoring_service.entity.RetryEntity;
import com.ccd.monitoring_service.rabbitmq.config.RabbitMQConfig;
import com.ccd.monitoring_service.repository.RetryRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.support.AmqpHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Slf4j
public class RetryHandlerService {
    private final RetryRepository retryRepository;
    private final ObjectMapper objectMapper; // JSON 변환용

    @RabbitListener(queues = RabbitMQConfig.QUEUE_RETRY)
    @Transactional
    public void handleRetry(LogMessageDto dto,
                            @Header(AmqpHeaders.RECEIVED_ROUTING_KEY) String routingKey) {
        log.warn("이벤트 수신, RoutingKey [{}], CORRELATION ID: [{}]", routingKey, dto.getCorrelationId());

        if (RabbitMQConfig.ROUTING_KEY_FAIL.equals(routingKey)) {
            handleNewFailure(dto);
        } else if (routingKey.contains(".retry.")) {
            handleRetryResult(dto);
        } else {
            log.warn("처리할 수 없는 라우팅 키:{}", routingKey);
        }
    }

    private void handleNewFailure(LogMessageDto dto) {
        if (retryRepository.existsByCorrelationId(dto.getCorrelationId())) {
            log.info("이미 등록된 실패 건입니다. 무시. ID: {}", dto.getCorrelationId());
            return;
        }

        try {
            log.info(">>> 신규 실패 등록. ID: {}", dto.getCorrelationId());
            String json = objectMapper.writeValueAsString(dto);
            RetryEntity entity = new RetryEntity(
                    dto.getCorrelationId(),
                    json,
                    dto.getServiceName()
            );
            // 신규 등록 시에는 다음 실행 시간만 잡고 끝 (스케줄러가 가져감)
            // 바로 실행하고 싶으면 planNextAttempt() 없이 저장하면 스케줄러가 즉시 가져감
            retryRepository.save(entity);

        } catch (JsonProcessingException e) {
            log.error("JSON 변환 실패", e);
        }
    }

    private void handleRetryResult(LogMessageDto dto) {
        RetryEntity entity = retryRepository.findByCorrelationId(dto.getCorrelationId())
                .stream().findFirst().orElse(null);

        if (entity == null) {
            log.warn("Not Registered Correlation ID: {}", dto.getCorrelationId());
            return;
        }

        if (dto.getLogType() == LogType.SYSTEM) { // 성공으로 간주
            log.info("재시도 성공! ID: {}", dto.getCorrelationId());
            entity.markAsSuccess();
        } else {
            log.warn("재시도 또 실패. 다음 일정 예약. ID: {}", dto.getCorrelationId());
            entity.planNextAttempt(); // 시간 뒤로 미루기
        }
    }
}


