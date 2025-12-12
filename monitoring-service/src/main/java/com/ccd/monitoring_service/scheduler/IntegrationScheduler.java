package com.ccd.monitoring_service.scheduler;

import com.ccd.monitoring_service.entity.BaseLogEntity;
import com.ccd.monitoring_service.entity.ErrorLogEntity;
import com.ccd.monitoring_service.entity.RetryEntity;
import com.ccd.monitoring_service.entity.SystemLogEntity;
import com.ccd.monitoring_service.repository.ErrorLogRepository;
import com.ccd.monitoring_service.repository.RetryRepository;
import com.ccd.monitoring_service.repository.SystemLogRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

@Component
@RequiredArgsConstructor
@Slf4j
public class IntegrationScheduler {

    private final SystemLogRepository systemLogRepository;
    private final ErrorLogRepository errorLogRepository;
    private final RetryRepository retryRepository;

    @Scheduled(fixedDelay = 60000) // 1분마다
    @Transactional
    public void checkTransactionIntegrity() {
        LocalDateTime cutoffTime = LocalDateTime.now().minusMinutes(10);

        // 1. 문제가 있는 트랜잭션의 시작점(Start Log)만 먼저 가져옴
        List<SystemLogEntity> failedTransactions =
                systemLogRepository.findIncompleteTransactionsNative(cutoffTime);

        for (SystemLogEntity startLog : failedTransactions) {
            processRetryWithDetail(startLog);
        }
    }

   private void processRetryWithDetail(SystemLogEntity startLog) {
        String correlationId = startLog.getCorrelationId();

        // 1. 전체 이력 가져오기
        List<BaseLogEntity> history = getFullTransactionHistory(correlationId);

        // 2. [수정됨] 누락된 이벤트 정밀 분석
        List<String> missingAnalysis = analyzeMissingEvents(history);

        try {
            // 4. ErrorLog 저장
            for(String missingItem : missingAnalysis) {
                String targetService;
                String detailReason;

                // [핵심 로직] 괄호()를 기준으로 서비스명과 상세 내용을 분리
                if (missingItem.contains("(") && missingItem.endsWith(")")) {
                    int openParenIndex = missingItem.indexOf("(");
                    // 괄호 앞부분: "notification-service"
                    targetService = missingItem.substring(0, openParenIndex);
                    // 괄호 안부분: "ImageSaved"
                    detailReason = missingItem.substring(openParenIndex + 1, missingItem.length() - 1);
                } else {
                    // 괄호가 없는 경우 (예: tagging, embedding-service)
                    targetService = missingItem;
                    detailReason = "Event missing over 10 mins."; // 기본 사유
                }

                ErrorLogEntity summaryError = new ErrorLogEntity(
                        correlationId,
                        targetService,
                        "Event missing over 10 mins",
                        null,
                        "INTEGRITY_FAIL",
                        ""
                );
                errorLogRepository.save(summaryError);

                // 5. RetryQueue 등록
                RetryEntity retry = new RetryEntity(
                        correlationId,
                        "crud",
                        targetService
                );
                retry.markAsFail(detailReason);
                retryRepository.save(retry);

                log.info("[IntegrityCheck] Retry registered for {}.", correlationId);
            }
        } catch (Exception e) {
            log.error("Failed to process retry for {}", correlationId, e);
        }
    }

    private List<BaseLogEntity> getFullTransactionHistory(String correlationId) {
        // 1. 시스템 로그 조회
        List<SystemLogEntity> systems = systemLogRepository.findByCorrelationId(correlationId);

        // 2. 에러 로그 조회
        List<ErrorLogEntity> errors = errorLogRepository.findByCorrelationId(correlationId);

        // 3. 합치기 (BaseLogEntity 리스트로 통합)
        List<BaseLogEntity> fullHistory = new ArrayList<>();
        fullHistory.addAll(systems);
        fullHistory.addAll(errors);

        // 4. 시간순 정렬 (createdAt 기준)
        fullHistory.sort(Comparator.comparing(BaseLogEntity::getCreatedAt));

        return fullHistory;
    }

    private List<String> analyzeMissingEvents(List<BaseLogEntity> history) {
        // 1. 체크할 플래그 변수들 초기화
        boolean hasTagging = false;
        boolean hasEmbedding = false;
        boolean hasNotiForCrud = false; // "service.crud.item.saved.img" 관련 알림
        boolean hasNotiForTagging = false; // "service.tagging.success" 관련 알림

        // 2. 히스토리 전체 순회하며 플래그 업데이트
        for (BaseLogEntity log : history) {
            // 성공 로그(SystemLogEntity)만 체크합니다.
            if (log instanceof SystemLogEntity sysLog) {
                String serviceName = sysLog.getServiceName();
                String message = sysLog.getMessage(); // BaseLogEntity에 있음

                // A. Tagging 확인
                if ("tagging".equals(serviceName)) {
                    hasTagging = true;
                }

                // B. Embedding 확인
                if ("embedding-service".equals(serviceName)) {
                    hasEmbedding = true;
                }

                // C. Notification 확인 (message 내용으로 구분)
                // 서비스 이름이 'notification' 이거나 이벤트 타입이 'service.notification.sent' 인 경우
                if ("notification-service".equals(serviceName)) {
                    if (message != null) {
                        if (message.contains("service.crud.item.saved.img")) {
                            hasNotiForCrud = true;
                        } else if (message.contains("service.tagging.success")) {
                            hasNotiForTagging = true;
                        }
                    }
                }
            }
        }

        // 3. 누락된 항목 수집
        List<String> missingList = new ArrayList<>();

        if (!hasTagging) missingList.add("tagging");
        if (!hasEmbedding) missingList.add("embedding-service");
        if (!hasNotiForCrud) missingList.add("notification-service(ImageSaved)");
        if (!hasNotiForTagging) missingList.add("notification-service(TaggingSuccess)");

        // 4. 결과 메시지 생성
        if (missingList.isEmpty()) {
            log.error("Unknown Error (All events seem present)");
        } else {
            log.info("find missing events: {}", missingList);
        }
        return missingList;
    }
}
