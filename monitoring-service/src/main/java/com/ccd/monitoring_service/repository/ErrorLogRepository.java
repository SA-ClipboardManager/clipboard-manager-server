package com.ccd.monitoring_service.repository;

import com.ccd.monitoring_service.entity.ErrorLogEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ErrorLogRepository extends JpaRepository<ErrorLogEntity,Long> {

    List<ErrorLogEntity> findByCorrelationId(String correlationId);
}
