package com.ccd.monitoring_service.repository;

import com.ccd.monitoring_service.entity.RetryEntity;
import com.ccd.monitoring_service.entity.RetryStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.time.LocalDateTime;
import java.util.List;

public interface RetryRepository extends JpaRepository<RetryEntity, Long> {
    List<RetryEntity> findByCorrelationId(String correlationId);

    boolean existsByCorrelationId(String correlationId);

   @Query("SELECT r FROM RetryEntity r WHERE r.status = :retryStatus AND r.nextAttemptAt < :now")
    List<RetryEntity> findMessageByNextAttemptAndRetryStatus(LocalDateTime now, RetryStatus retryStatus);
}
