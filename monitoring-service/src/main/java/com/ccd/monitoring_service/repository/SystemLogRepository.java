package com.ccd.monitoring_service.repository;

import com.ccd.monitoring_service.entity.SystemLogEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;

public interface SystemLogRepository extends JpaRepository<SystemLogEntity, Long> {


    List<SystemLogEntity> findByCorrelationId(String correlationId);

    @Query(value = """
        SELECT s.* FROM system_logs s
        WHERE s.service_name = 'crud-service'       -- 1. 시작점(Payload 보유) 찾기
          AND s.created_at < :cutoffTime    -- 2. 10분이 지난 건만
          AND NOT EXISTS (                  -- 3. 이미 재시도 중인 건 제외
              SELECT 1 FROM retry r WHERE r.correlation_id = s.correlation_id
          )
          AND s.correlation_id IN (         -- 4. 조건 미달성 ID 찾기 (서브쿼리)
              SELECT combined.correlation_id
              FROM (
                  -- SystemLog와 ErrorLog를 위아래로 합침 (UNION ALL)
                  SELECT correlation_id, service_name FROM system_logs
                  UNION ALL
                  SELECT correlation_id, service_name FROM error_logs
              ) combined
              WHERE combined.correlation_id = s.correlation_id
              GROUP BY combined.correlation_id
              HAVING
                 -- [조건 체크]
                 -- crud 1개 미만 OR embedding 1개 미만 OR tagging 1개 미만 OR notification 2개 미만
                 COUNT(CASE WHEN service_name = 'crud-service' THEN 1 END) < 1
                 OR COUNT(CASE WHEN service_name = 'embedding-service' THEN 1 END) < 1
                 OR COUNT(CASE WHEN service_name = 'tagging' THEN 1 END) < 1
                 OR COUNT(CASE WHEN service_name = 'notification-service' THEN 1 END) < 2
          )
        """, nativeQuery = true)
    List<SystemLogEntity> findIncompleteTransactionsNative(
            @Param("cutoffTime") LocalDateTime cutoffTime
    );
}
