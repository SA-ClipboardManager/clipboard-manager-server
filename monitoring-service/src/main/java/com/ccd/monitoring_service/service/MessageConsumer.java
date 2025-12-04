package com.ccd.monitoring_service.service;

import com.ccd.monitoring_service.dto.LogMessageDto;
import com.ccd.monitoring_service.dto.LogType;
import com.ccd.monitoring_service.entity.ErrorLogEntity;
import com.ccd.monitoring_service.entity.SystemLogEntity;
import com.ccd.monitoring_service.rabbitmq.config.RabbitMQConfig;
import com.ccd.monitoring_service.repository.ErrorLogRepository;
import com.ccd.monitoring_service.repository.SystemLogRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Slf4j
@RequiredArgsConstructor
public class MessageConsumer {
    private final SystemLogRepository systemLogRepository;
    private final ErrorLogRepository errorLogRepository;
    private final RabbitTemplate rabbitTemplate;

    @RabbitListener(queues = RabbitMQConfig.QUEUE_MAIN)
    @Transactional
    public void receiveMessage(LogMessageDto dto) {
           log.info("수신 ID: {}", dto.getCorrelationId());

        try {
            // =========================
            // ★ 비즈니스 로직 수행 구역 ★
           saveLogToDatabase(dto);

           if(dto.getLogType() == LogType.ERROR){
               log.info("Service Failed. Send to Retry Queue");
               rabbitTemplate.convertAndSend(
                       RabbitMQConfig.MONITORING_RECOVERY_EXCHANGE,
                       RabbitMQConfig.ROUTING_KEY_FAIL,
                       dto
               );
           }
            // =========================

        } catch (Exception e) {
            log.error("처리 실패! 재시도 불가! 원인: {}", e.getMessage());
            }
        }

    private void saveLogToDatabase(LogMessageDto dto) {
        if (dto.getLogType() == LogType.SYSTEM) {
            saveSystemLog(dto);

        } else if (dto.getLogType() == LogType.ERROR) {
            saveErrorLog(dto);

        } else {
            log.warn("알 수 없는 로그 타입: {}", dto.getLogType());
        }
    }

    private void saveErrorLog(LogMessageDto dto) {
        ErrorLogEntity entity = new ErrorLogEntity(
                dto.getCorrelationId(),
                dto.getServiceName(),
                dto.getMessage(),
                dto.getStackTrace(),
                dto.getExceptionType()
        );
        errorLogRepository.save(entity);
        log.info("ErrorLog 저장 완료");
    }

    private void saveSystemLog(LogMessageDto dto) {
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
