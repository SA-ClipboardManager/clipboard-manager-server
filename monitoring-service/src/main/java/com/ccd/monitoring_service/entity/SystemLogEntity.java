package com.ccd.monitoring_service.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Getter
@Table(name = "system_logs", indexes = @Index(name = "idx_correlation_id", columnList = "correlationId"))
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class SystemLogEntity extends BaseLogEntity {
    private String logLevel;

    public SystemLogEntity(String correlationId, String serviceName, String message, String logLevel) {
        super(correlationId, serviceName, message);
        this.logLevel = logLevel;
    }
}
