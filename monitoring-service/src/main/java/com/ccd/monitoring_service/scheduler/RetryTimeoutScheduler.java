package com.ccd.monitoring_service.scheduler;

import com.ccd.monitoring_service.entity.RetryEntity;
import com.ccd.monitoring_service.entity.RetryHistoryEntity;
import com.ccd.monitoring_service.entity.RetryStatus;
import com.ccd.monitoring_service.repository.RetryHistoryRepository;
import com.ccd.monitoring_service.repository.RetryRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Slf4j
@RequiredArgsConstructor
@Component
public class RetryTimeoutScheduler {

    private final RetryRepository retryRepository;
    private final RetryHistoryRepository retryHistoryRepository;
    private static final Long maxPendingMinute = 5L;

    @Scheduled(fixedRate = 20000) //20초마다 반복
    @Transactional
    public void saveHistory() {
        LocalDateTime now = LocalDateTime.now();

        List<RetryEntity> targets = retryRepository.findMessageByNextAttemptAndRetryStatus(now, RetryStatus.PENDING);
        if (targets.isEmpty()) return;

        for (RetryEntity snapshot : targets) {
            try {
                RetryEntity target = retryRepository.findById(snapshot.getId())
                    .orElse(null);

                if(target == null) continue;

                //이미 상태가 바뀌었으면 PASS (Consumer 우선권)
                if(target.getStatus() != RetryStatus.PENDING) continue;

                //Pending 기준 시간보다 오래 지속됐으면 Fail 처리
                if (target.getNextAttemptAt().isBefore(now.minusMinutes(maxPendingMinute))) {
                    // retry table에 fail 처리
                    target.markAsFail("Pended more than " + maxPendingMinute + "minutes");
                    log.warn("[RetryTimeout] FAIL 처리됨 | id={} service={} reason={}",
                            target.getCorrelationId(),
                            target.getServiceName(),
                            target.getFailReason());

                    //retryHistory table 저장
                    log.info("save retry history | Correlation ID: [{}]", target.getCorrelationId());
                    saveHistory(target, target.getFailReason());

                }
            }catch (ObjectOptimisticLockingFailureException e){
                //version mismatch가 있으면 OptimisticLock 예외 발생
                log.info("[RetryTimeout] SKIP — Consumer가 먼저 처리하여 version 충돌 | id={}",
                    snapshot.getCorrelationId());
            }
        }
    }

    private void saveHistory(RetryEntity retryEntity,
                             String message) {
        RetryHistoryEntity history = new RetryHistoryEntity(
                retryEntity.getCorrelationId(),
                retryEntity.getRetryCount(),
                RetryStatus.FAIL,
                message
        );
        retryHistoryRepository.save(history);
    }

}
