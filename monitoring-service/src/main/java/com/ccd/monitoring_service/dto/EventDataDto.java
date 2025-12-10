package com.ccd.monitoring_service.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.*;

@Data
@Builder
@ToString
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class EventDataDto {
    // --- [공통 필드] ---
    @JsonProperty("correlation_id")
    @JsonAlias({"correlationId"})
    private String correlationId; // 트랜잭션 추적 ID (필수)
    private String serviceName;   // 보낸 서비스 명 (예: payment)
    private String message;       // 로그 메시지
    private LogType logType;      // SYSTEM 또는 ERROR (필수)

    // --- [일반 로그용 필드] ---
    private String logLevel;      // INFO, DEBUG 등 (SystemLog용)

    // --- [에러 로그용 필드] ---e
    private String stackTrace;    // 에러 상세 (ErrorLog용)
    private String exceptionType; // 예외 클래스 이름 (ErrorLog용)

    // --- [태깅용 필드] --- 실패 시 저장
    @JsonProperty("data_id")
    @JsonAlias({"dataId"})
    private String dataId;          // tagging 대상 UUID
    @JsonProperty("user_id")
    @JsonAlias({"userId"})
    private String userId;          // tagging 요청한 유저
    @JsonProperty("file_path")
    @JsonAlias({"filePath"})
    private String filePath;        // 파일 경로
    private String modelSource;     // 예: mobilenetv3
}
