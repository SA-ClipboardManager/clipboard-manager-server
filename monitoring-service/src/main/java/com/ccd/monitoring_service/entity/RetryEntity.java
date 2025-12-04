package com.ccd.monitoring_service.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;

@Entity
@Getter
@Table(name = "compensating", indexes = @Index(name = "idx_correlation_id", columnList = "correlationId"))
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@EntityListeners(AuditingEntityListener.class)
public class RetryEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String correlationId;

    @Lob // 메시지 내용을 통째로 저장 (JSON 문자열 등)
    private String messageJson;

    @Column(nullable = false)
    private String serviceName;

    @Column(nullable = false)
    @Enumerated(EnumType.STRING)
    private RetryStatus status; // PENDING(대기), SUCCESS(성공), FAIL(실패)

    private String failReason; // 실패했을 때 원인 기록

    private int retryCount;

    private LocalDateTime nextAttemptAt;


    @CreatedDate
    private LocalDateTime createdAt; // 실패 발생 시간

    @LastModifiedDate
    private LocalDateTime updatedAt; // 처리 시간

    public RetryEntity(String correlationId,String messageJson, String serviceName) {
        this.correlationId = correlationId;
        this.messageJson = messageJson;
        this.serviceName = serviceName;
        this.retryCount = 0;
        this.nextAttemptAt = LocalDateTime.now();
        this.status = RetryStatus.PENDING; // 처음엔 대기 상태로 시작
    }
    // 상태 변경 메서드 (Setter 대신 사용)
    public void markAsSuccess() {
        this.status = RetryStatus.SUCCESS;
    }

    public void markAsFail(String reason) {
        this.status = RetryStatus.FAIL;
        this.failReason = reason;
    }

    public void planNextAttempt() {
        this.retryCount++;
        // 예: 1분 -> 4분 -> 9분 뒤 (retryCount^2 분)
        long delayMinutes = (long) Math.pow(this.retryCount, 2);
        this.nextAttemptAt = LocalDateTime.now().plusMinutes(delayMinutes);
    }
}

