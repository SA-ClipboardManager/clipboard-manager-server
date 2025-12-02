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
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Slf4j
@RequiredArgsConstructor
public class MessageConsumer {
    private final SystemLogRepository systemLogRepository;
    private final ErrorLogRepository errorLogRepository;

    @RabbitListener(queues = RabbitMQConfig.QUEUE_NAME)
    @Transactional
    public void receiveMessage(LogMessageDto dto) {
        log.info("RabbitMQ 수신 [{}]: {}", dto.getCorrelationId(), dto);

        try {
            if (dto.getLogType() == LogType.SYSTEM) {
                saveSystemLog(dto);
            } else if (dto.getLogType() == LogType.ERROR) {
                saveErrorLog(dto);
            } else {
                log.warn("알 수 없는 로그 타입입니다: {}", dto.getLogType());
            }
        } catch (Exception e) {
            log.error("로그 저장 실패! correlationId: {}", dto.getCorrelationId(), e);
            // 여기서 throw e;를 해야 RabbitMQ가 실패 처리(Nack) 후 재시도/DLQ 이동을 함
            throw e;
        }


        /* TODO Business logic
            insert to db OR
            on failed retry OR
            cancel for all
         */
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
    }

    private void saveSystemLog(LogMessageDto dto) {
        SystemLogEntity entity = new SystemLogEntity(
                dto.getCorrelationId(),
                dto.getServiceName(),
                dto.getMessage(),
                dto.getLogLevel()
        );
        systemLogRepository.save(entity);
    }
}
