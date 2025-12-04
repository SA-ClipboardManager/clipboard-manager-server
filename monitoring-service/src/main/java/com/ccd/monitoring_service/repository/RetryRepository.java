package com.ccd.monitoring_service.repository;

import com.ccd.monitoring_service.entity.RetryEntity;
import com.ccd.monitoring_service.entity.RetryStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;

public interface RetryRepository extends JpaRepository<RetryEntity, Long> {
    List<RetryEntity> findByCorrelationId(String correlationId);

    boolean existsByCorrelationId(String correlationId);

    List<RetryEntity> findByNextAttemptAtBeforeAndStatus(LocalDateTime nextAttemptAtBefore, RetryStatus status);
}
