package com.ccd.monitoring_service.schedular;

import com.ccd.monitoring_service.dto.LogMessageDto;
import com.ccd.monitoring_service.entity.RetryEntity;
import com.ccd.monitoring_service.entity.RetryStatus;
import com.ccd.monitoring_service.rabbitmq.config.RabbitMQConfig;
import com.ccd.monitoring_service.repository.RetryRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.transaction.Transactional;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.List;

@Component
@RequiredArgsConstructor
@Slf4j
public class RetryScheduler {

    private final RetryRepository retryRepository;
    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper objectMapper;

    @Scheduled(fixedDelay = 10000)
    @Transactional
    public void retryFailedMessages() {
        LocalDateTime now = LocalDateTime.now();

        List<RetryEntity> targets =
                retryRepository.findByNextAttemptAtBeforeAndStatus(now, RetryStatus.PENDING);
        if (targets.isEmpty()) {
            return;
        }
        for (RetryEntity retryEntity : targets) {
            try {
                LogMessageDto dto = objectMapper.readValue(retryEntity.getMessageJson(), LogMessageDto.class);
                rabbitTemplate.convertAndSend(
                        RabbitMQConfig.MONITORING_RECOVERY_EXCHANGE,
                        retryEntity.getServiceName() + ".do.retry", dto
                );

            } catch (Exception e) {
                log.error("재발송 중 에러 발생 (심각). 일단 다음 텀에 다시 시도.", e);
                // 재시도 횟수가 너무 많으면(예: 10회) delete 하거나 별도 알림 보내는 로직 추가 필요 OR 보상 트랜잭션
            }
        }

    }
}
