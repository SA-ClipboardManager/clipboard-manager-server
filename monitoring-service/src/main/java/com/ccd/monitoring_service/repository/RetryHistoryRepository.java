package com.ccd.monitoring_service.repository;

import com.ccd.monitoring_service.entity.RetryHistoryEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RetryHistoryRepository extends JpaRepository<RetryHistoryEntity, Long> {
}
