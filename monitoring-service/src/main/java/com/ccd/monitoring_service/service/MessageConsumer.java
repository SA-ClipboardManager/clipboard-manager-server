package com.ccd.monitoring_service.service;

import com.ccd.monitoring_service.dto.EventDataDto;
import com.ccd.monitoring_service.dto.LogType;
import com.ccd.monitoring_service.entity.ErrorLogEntity;
import com.ccd.monitoring_service.entity.SystemLogEntity;
import com.ccd.monitoring_service.rabbitmq.config.RabbitMQConfig;
import com.ccd.monitoring_service.repository.ErrorLogRepository;
import com.ccd.monitoring_service.repository.SystemLogRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.Map;

@Service
@Slf4j
@RequiredArgsConstructor
public class MessageConsumer {
    private final SystemLogRepository systemLogRepository;
    private final ErrorLogRepository errorLogRepository;
    private final RabbitTemplate rabbitTemplate;

    @RabbitListener(queues = RabbitMQConfig.QUEUE_MAIN)
    @Transactional
    public void receiveMessage(EventDataDto dto) {
           log.info("수신 ID: {}", dto.getCorrelationId());

        try {
            // =========================
            // ★ 비즈니스 로직 수행 구역 ★
           saveLogToDatabase(dto);

           if(dto.getLogType() == LogType.ERROR){
               if(dto.getServiceName().equals("crud")){ //재시도 X
                   log.info("[{}] service Failed. Compensate",  dto.getServiceName());
               }else {

                   log.info("Service Failed. Send to Retry Queue");
                   rabbitTemplate.convertAndSend(
                           RabbitMQConfig.MONITORING_RECOVERY_EXCHANGE,
                           RabbitMQConfig.ROUTING_KEY_FAIL,
                           dto
                   );
               }
           }
            // =========================

        } catch (Exception e) {
            log.error("처리 실패! 재시도 불가! 원인: {}", e.getMessage());
            }
        }

    private void saveLogToDatabase(EventDataDto dto) {
        if (dto.getLogType() == LogType.SYSTEM) {
            saveSystemLog(dto);

        } else if (dto.getLogType() == LogType.ERROR) {
            saveErrorLog(dto);

        } else {
            log.warn("알 수 없는 로그 타입: {}", dto.getLogType());
        }
    }

    private void saveErrorLog(EventDataDto dto) {
        try {
            ObjectMapper mapper = new ObjectMapper();

            // 태깅 데이터만 뽑아 JSON으로 저장
            Map<String, Object> taggingMap = new HashMap<>();
            taggingMap.put("dataId", dto.getDataId());
            taggingMap.put("userId", dto.getUserId());
            taggingMap.put("filePath", dto.getFilePath());
            taggingMap.put("modelSource", dto.getModelSource());
            taggingMap.put("tags", dto.getTags());

            String tagJson = mapper.writeValueAsString(taggingMap);

            ErrorLogEntity entity = new ErrorLogEntity(
                    dto.getCorrelationId(),
                    dto.getServiceName(),
                    dto.getMessage(),
                    dto.getStackTrace(),
                    dto.getExceptionType(),
                    tagJson
            );
            errorLogRepository.save(entity);
            log.info("ErrorLog 저장 완료");
        } catch (Exception e) {
            log.error("ErrorLog 저장 실패", e);
        }
    }

    private void saveSystemLog(EventDataDto dto) {
        SystemLogEntity entity = new SystemLogEntity(
                dto.getCorrelationId(),
                dto.getServiceName(),
                dto.getMessage(),
                dto.getLogLevel()
        );
        systemLogRepository.save(entity);
        log.info("SystemLog 저장 완료");
    }
}
