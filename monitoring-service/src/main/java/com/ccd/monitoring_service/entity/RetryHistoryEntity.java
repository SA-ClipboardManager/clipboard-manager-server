package com.ccd.monitoring_service.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;

@Entity
@Getter
@Table(name = "retry_history", indexes = @Index(name = "idx_hist_correlation_id", columnList = "correlationId"))
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@EntityListeners(AuditingEntityListener.class) // 생성 시간 자동 저장을 위해 추가
public class RetryHistoryEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String correlationId; // 어떤 트랜잭션인지
    private int attemptNumber;    // 몇 번째 시도였는지

    @Enumerated(EnumType.STRING)
    private RetryStatus status;

    @Column(columnDefinition = "TEXT")
    private String message;    // 왜 실패했는지

    @CreatedDate
    @Column(updatable = false)
    private LocalDateTime recordedAt; // 언제 시도했는지

    public RetryHistoryEntity(String correlationId, int attemptNumber, RetryStatus status, String failReason) {
        this.correlationId = correlationId;
        this.attemptNumber = attemptNumber;
        this.status = status;
        this.message = failReason;
        this.recordedAt = LocalDateTime.now();
    }
}
