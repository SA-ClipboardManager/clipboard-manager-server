package com.ccd.monitoring_service.schedular;

import com.fasterxml.jackson.core.type.TypeReference;
import com.ccd.monitoring_service.dto.EventDataDto;
import com.ccd.monitoring_service.dto.LogType;
import com.ccd.monitoring_service.dto.TagDto;
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
import java.util.Map;

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
                retryRepository.findMessageToBeSent(now, RetryStatus.FAIL);
        if (targets.isEmpty()) {
            return;
        }
        for (RetryEntity target : targets) {
            log.info("Retry Correlation ID: [{}], Service: [{}]", target.getCorrelationId(), target.getServiceName());
            try {
                // 1) tagInfoJson 파싱
                Map<String, Object> tagMap =
                        objectMapper.readValue(
                                target.getTagInfoJson(),
                                new TypeReference<Map<String, Object>>() {
                                }
                        );

                // 2) tags 파싱 (List<Map> → List<TagDto>)
                List<Map<String, Object>> rawTags =
                        (List<Map<String, Object>>) tagMap.get("tags");

                List<TagDto> parsedTags = rawTags == null ? null :
                        rawTags.stream()
                                .map(m -> new TagDto(
                                        (String) m.get("label"),
                                        Float.parseFloat(m.get("score").toString())
                                ))
                                .toList();
                // 3) EventDataDto 복원
                EventDataDto dto = EventDataDto.builder()
                        .correlationId(target.getCorrelationId())
                        .serviceName(target.getServiceName())
                        .logType(LogType.SYSTEM) // 재시도 전송은 SYSTEM
                        .message("Retry Attempt")

                        .dataId((String) tagMap.get("dataId"))
                        .userId((String) tagMap.get("userId"))
                        .filePath((String) tagMap.get("filePath"))
                        .modelSource((String) tagMap.get("modelSource"))
                        .tags(parsedTags)
                        .build();
                target.markAsPending();
                rabbitTemplate.convertAndSend(
                        RabbitMQConfig.MONITORING_RECOVERY_EXCHANGE,
                        target.getServiceName() + ".do.retry",
                        dto
                );
                log.info("송신 | send to Exchange: [{}]", RabbitMQConfig.MONITORING_RECOVERY_EXCHANGE);
            } catch (Exception e) {
                log.error("재발송 중 에러 발생 (심각)", e);
                // 재시도 횟수가 너무 많으면(예: 10회) delete 하거나 별도 알림 보내는 로직 추가 필요 OR 보상 트랜잭션
            }
        }

    }
}
