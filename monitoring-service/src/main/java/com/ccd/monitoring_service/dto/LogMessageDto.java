package com.ccd.monitoring_service.dto;

import lombok.*;

@Data
@Builder
@ToString
@NoArgsConstructor
@AllArgsConstructor
public class LogMessageDto {
    // --- [공통 필드] ---
    private String correlationId; // 트랜잭션 추적 ID (필수)
    private String serviceName;   // 보낸 서비스 명 (예: payment)
    private String message;       // 로그 메시지
    private LogType logType;      // SYSTEM 또는 ERROR (필수)

    // --- [일반 로그용 필드] ---
    private String logLevel;      // INFO, DEBUG 등 (SystemLog용)

    // --- [에러 로그용 필드] ---
    private String stackTrace;    // 에러 상세 (ErrorLog용)
    private String exceptionType; // 예외 클래스 이름 (ErrorLog용)
}
