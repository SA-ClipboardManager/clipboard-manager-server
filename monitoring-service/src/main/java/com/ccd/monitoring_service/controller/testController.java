package com.ccd.monitoring_service.controller;

import com.ccd.monitoring_service.dto.LogMessageDto;
import com.ccd.monitoring_service.dto.LogType;
import com.ccd.monitoring_service.rabbitmq.config.RabbitMQConfig;
import lombok.RequiredArgsConstructor;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequiredArgsConstructor
public class testController {
    private final RabbitTemplate rabbitTemplate;

    // 1. 일반 로그 테스트 (브라우저에서 호출 가능)
    // http://localhost:8080/test/system
    @GetMapping("/test/system")
    public String sendSystemLog() {
        String correlationId = UUID.randomUUID().toString();

        LogMessageDto dto = LogMessageDto.builder()
                .correlationId(correlationId)
                .serviceName("payment-service") // 가상의 서비스 이름
                .message("결제가 성공적으로 완료되었습니다.")
                .logType(LogType.SYSTEM)
                .logLevel("INFO")
                .build();

        rabbitTemplate.convertAndSend(
                RabbitMQConfig.MONITORING_MAIN_EXCHANGE,
                RabbitMQConfig.ROUTING_KEY_MAIN_PATTERN,
                dto
        );

        return "System Log Sent! ID: " + correlationId;
    }

    // 2. 에러 로그 테스트
    // http://localhost:8080/test/error
    @GetMapping("/test/error")
    public String sendErrorLog() {
        String correlationId = UUID.randomUUID().toString();

        LogMessageDto dto = LogMessageDto.builder()
                .correlationId(correlationId)
                .serviceName("order-service")
                .message("주문 처리 중 NullPointerException 발생")
                .logType(LogType.ERROR)
                .exceptionType("java.lang.NullPointerException")
                .stackTrace("at com.artium.order.service.OrderService.process(OrderService.java:45)...")
                .build();

        rabbitTemplate.convertAndSend(
                RabbitMQConfig.MONITORING_MAIN_EXCHANGE,
                RabbitMQConfig.ROUTING_KEY_MAIN_PATTERN,
                dto
        );

        return "Error Log Sent! ID: " + correlationId;
    }
}
