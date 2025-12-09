package com.ccd.monitoring_service.schedular;

import com.ccd.monitoring_service.entity.RetryEntity;
import com.ccd.monitoring_service.entity.RetryHistoryEntity;
import com.ccd.monitoring_service.entity.RetryStatus;
import com.ccd.monitoring_service.repository.RetryHistoryRepository;
import com.ccd.monitoring_service.repository.RetryRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
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
    private final Long maxPendingMinute = 2L;

    @Scheduled(fixedRate = 20000)
    @Transactional
    public void saveHistory() {
        LocalDateTime now = LocalDateTime.now();

        List<RetryEntity> targets = retryRepository.findMessageByNextAttemptAndRetryStatus(now, RetryStatus.PENDING);
        if (targets.isEmpty()) return;

        for (RetryEntity target : targets) {
            //Pending 2분 지속이면 Fail 처리
            if (target.getNextAttemptAt().isBefore(now.minusMinutes(maxPendingMinute))) {
                // retry table에 fail 처리
                log.info("Mark pending retry as fail | Correlation ID: [{}]", target.getCorrelationId());
                target.markAsFail("Pended more than " + maxPendingMinute + "minutes");

                //retryHistory table 저장
                log.info("save retry history | Correlation ID: [{}]", target.getCorrelationId());
                saveHistory(target, target.getFailReason());

            }
        }
    }

    private void saveHistory(RetryEntity retryEntity,
                             String message) {
        RetryHistoryEntity history = new RetryHistoryEntity(
                retryEntity.getCorrelationId(),
                retryEntity.getRetryCount(),
                RetryStatus.PENDING,
                message
        );
        retryHistoryRepository.save(history);
    }

}
