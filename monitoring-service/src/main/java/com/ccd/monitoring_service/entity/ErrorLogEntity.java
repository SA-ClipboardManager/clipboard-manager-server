package com.ccd.monitoring_service.entity;


import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Getter
@Table(name = "error_logs", indexes = @Index(name = "idx_correlation_id", columnList = "correlationId"))
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ErrorLogEntity extends BaseLogEntity {
    @Column(columnDefinition = "LONGTEXT")
    private String stackTrace;

    @Column
    private String exceptionType;

    @Column(columnDefinition = "LONGTEXT")
    private String tagInfoJson;

    public ErrorLogEntity(String correlationId, String serviceName, String message, String stackTrace, String exceptionType, String tagInfoJson) {
        super(correlationId, serviceName, message);
        this.stackTrace = stackTrace;
        this.exceptionType = exceptionType;
        this.tagInfoJson = tagInfoJson;
    }
}
