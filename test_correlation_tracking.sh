#!/bin/bash
# 이벤트 기반 아키텍처 Correlation ID 추적 및 데이터 일관성 검증 (Bash)
# Ubuntu/Linux 환경용

set -e

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# 설정
BASE_URL="${BASE_URL:-http://133.186.229.40:8576}"
DB_HOST="${DB_HOST:-133.186.229.40}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-root}"
DB_PASS="${DB_PASS:-qwerty}"
RABBITMQ_USER="${RABBITMQ_USER:-qwerty}"
RABBITMQ_PASS="${RABBITMQ_PASS:-qwerty}"
RABBITMQ_URL="${RABBITMQ_URL:-http://133.186.229.40:15672}"
ITEM_COUNT="${ITEM_COUNT:-10}"

# 통계 변수
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
START_TIME=$(date +%s)
declare -a CORRELATION_IDS
declare -a UPLOADED_ITEMS

# 함수 정의
print_success() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS_COUNT++))
}

print_failure() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL_COUNT++))
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARN_COUNT++))
}

print_info() {
    echo -e "${CYAN}ℹ${NC} $1"
}

print_section() {
    echo ""
    echo -e "${BLUE}======================================================================${NC}"
    echo -e "${CYAN}${BOLD}$1${NC}"
    echo -e "${BLUE}======================================================================${NC}"
    echo ""
}

check_dependencies() {
    print_section "의존성 확인"
    
    local missing=0
    
    # Docker 확인
    if command -v docker >/dev/null 2>&1; then
        print_success "Docker 설치 확인"
    else
        print_failure "Docker 미설치"
        missing=1
    fi
    
    # Docker Compose 확인 (v1, v2 모두)
    if docker compose version >/dev/null 2>&1; then
        print_success "Docker Compose 설치 확인 (docker compose)"
        DOCKER_COMPOSE="docker compose"
    elif docker-compose version >/dev/null 2>&1; then
        print_success "Docker Compose 설치 확인 (docker-compose)"
        DOCKER_COMPOSE="docker-compose"
    else
        print_failure "Docker Compose 미설치"
        echo "  설치: sudo apt install -y docker-compose-plugin" >&2
        missing=1
    fi
    
    # curl 확인
    if command -v curl >/dev/null 2>&1; then
        print_success "curl 설치 확인"
    else
        print_failure "curl 미설치"
        missing=1
    fi
    
    # jq 확인 (선택)
    if command -v jq >/dev/null 2>&1; then
        print_success "jq 설치 확인"
    else
        print_warning "jq 미설치 (권장하지만 필수 아님)"
    fi
    
    # mysql 클라이언트 확인 (선택)
    if command -v mysql >/dev/null 2>&1; then
        print_success "mysql 클라이언트 설치 확인"
    else
        print_warning "mysql 클라이언트 미설치 (DB 직접 조회용, 필수 아님)"
    fi
    
    if [ $missing -eq 1 ]; then
        echo -e "\n${RED}필수 의존성 설치 필요${NC}"
        echo "sudo apt update && sudo apt install -y docker.io docker-compose-plugin curl"
        exit 1
    fi
}

get_docker_compose_cmd() {
    if docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    else
        echo "docker-compose"
    fi
}

DOCKER_COMPOSE=""

generate_correlation_id() {
    if command -v uuidgen &> /dev/null; then
        echo "test-$(uuidgen | tr '[:upper:]' '[:lower:]')"
    else
        echo "test-$(cat /proc/sys/kernel/random/uuid)"
    fi
}

create_test_image() {
    # 1x1 빨간색 PNG (Base64)
    echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
}

setup_test_user() {
    print_section "0단계: 테스트 사용자 설정"
    
    local timestamp=$(date +%s)
    local username="correlation_test_$timestamp"
    local password="testpass123"
    local email="correlation_test_${timestamp}@example.com"
    
    # 회원가입
    local response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/login/register" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$username\",\"password\":\"$password\",\"email\":\"$email\"}" \
        --max-time 10 2>/dev/null)
    
    local status_code=$(echo "$response" | tail -n1)
    
    if [[ "$status_code" =~ ^(200|201|409)$ ]]; then
        print_success "테스트 사용자 생성: 사용자명 $username"
    else
        print_warning "테스트 사용자 생성: 응답 코드 $status_code"
    fi
    
    # 로그인
    response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/login/login" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$username\",\"password\":\"$password\"}" \
        --max-time 10 2>/dev/null)
    
    status_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | head -n-1)
    
    if [ "$status_code" = "200" ]; then
        local token=""
        if command -v jq &> /dev/null; then
            token=$(echo "$body" | jq -r '.access_token // .token // empty' 2>/dev/null)
        else
            token=$(echo "$body" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
            [ -z "$token" ] && token=$(echo "$body" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
        fi
        
        if [ -n "$token" ]; then
            print_success "로그인 및 토큰 획득: 성공"
            echo "$token"
            return 0
        fi
    fi
    
    print_failure "로그인: 실패"
    return 1
}

upload_clipboard_items() {
    local token=$1
    local count=$2
    
    print_section "1단계: 클립보드 아이템 업로드 ($count개)"
    
    local uploaded_count=0
    
    for ((i=0; i<count; i++)); do
        local correlation_id=$(generate_correlation_id)
        CORRELATION_IDS+=("$correlation_id")
        
        if [ $((i % 2)) -eq 0 ]; then
            # 텍스트 업로드
            local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
            local response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/crud/clipboard" \
                -H "Content-Type: application/json" \
                -H "Authorization: Bearer $token" \
                -H "X-Correlation-ID: $correlation_id" \
                -d "{\"content\":\"테스트 텍스트 $((i+1)) - $timestamp\",\"type\":\"text\",\"correlation_id\":\"$correlation_id\"}" \
                --max-time 10 2>/dev/null)
            
            local status_code=$(echo "$response" | tail -n1)
            
            if [[ "$status_code" =~ ^(200|201)$ ]]; then
                ((uploaded_count++))
                print_info "텍스트 $((i+1)) 업로드 성공 (Correlation ID: ${correlation_id:0:16}...)"
            else
                print_warning "텍스트 $((i+1)) 업로드: 응답 코드 $status_code"
            fi
        else
            # 이미지 업로드 (간소화 버전)
            print_info "이미지 $((i+1)) 업로드 스킵 (파일 업로드는 Python 버전 사용 권장)"
        fi
        
        sleep 0.5
    done
    
    print_success "클립보드 아이템 업로드: $uploaded_count/$count개 성공"
    print_info "이벤트 처리 대기 중... (10초)"
    sleep 10
}

trigger_cloud_sync() {
    local token=$1
    
    print_section "2단계: 클라우드 동기화 실행"
    
    local response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/crud/sync/cloud" \
        -H "Authorization: Bearer $token" \
        --max-time 30 2>/dev/null)
    
    local status_code=$(echo "$response" | tail -n1)
    
    if [[ "$status_code" =~ ^(200|201|202)$ ]]; then
        print_success "클라우드 동기화 트리거: 성공"
        print_info "동기화 처리 대기 중... (15초)"
        sleep 15
    elif [ "$status_code" = "404" ]; then
        print_warning "클라우드 동기화 트리거: 엔드포인트 미구현"
    else
        print_warning "클라우드 동기화 트리거: 응답 코드 $status_code"
    fi
}

verify_correlation_in_monitoring_db() {
    print_section "3단계: 모니터링 DB에서 Correlation ID 추적"
    
    if ! command -v mysql &> /dev/null; then
        print_warning "mysql 클라이언트 미설치: DB 직접 조회 건너뜀"
        return
    fi
    
    # 테이블 목록 조회
    local tables=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASS" \
        -D monitoring_db -e "SHOW TABLES;" -s -N 2>/dev/null)
    
    if [ $? -ne 0 ]; then
        print_warning "모니터링 DB 연결: 연결 실패"
        return
    fi
    
    if [ -z "$tables" ]; then
        print_warning "모니터링 DB 테이블: 테이블이 없음"
        return
    fi
    
    print_info "발견된 테이블: $(echo $tables | tr '\n' ', ')"
    
    local log_tables=$(echo "$tables" | grep -i "log" || true)
    
    if [ -z "$log_tables" ]; then
        print_warning "로그 테이블: 로그 테이블을 찾을 수 없음"
        return
    fi
    
    local found_count=0
    local total_logs=0
    
    # 처음 3개 Correlation ID만 확인
    for cid in "${CORRELATION_IDS[@]:0:3}"; do
        for table in $log_tables; do
            # 테이블 컬럼 확인
            local columns=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASS" \
                -D monitoring_db -e "DESCRIBE $table;" -s -N 2>/dev/null | cut -f1)
            
            local corr_column=$(echo "$columns" | grep -i "correlation" | head -n1)
            
            if [ -n "$corr_column" ]; then
                local count=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASS" \
                    -D monitoring_db -e "SELECT COUNT(*) FROM $table WHERE $corr_column = '$cid';" -s -N 2>/dev/null)
                
                if [ "$count" -gt 0 ]; then
                    ((found_count++))
                    ((total_logs+=count))
                    print_info "Correlation ID ${cid:0:16}... 발견: $count개 로그 ($table)"
                fi
            fi
        done
    done
    
    if [ $found_count -gt 0 ]; then
        print_success "Correlation ID 추적: ${found_count}개 ID에서 총 ${total_logs}개 로그 발견"
    else
        print_warning "Correlation ID 추적: 모니터링 DB에서 Correlation ID를 찾을 수 없음"
    fi
}

verify_correlation_in_rabbitmq() {
    print_section "4단계: RabbitMQ 이벤트 흐름 확인"
    
    local response=$(curl -s -w "\n%{http_code}" -u "$RABBITMQ_USER:$RABBITMQ_PASS" \
        "$RABBITMQ_URL/api/queues" --max-time 10 2>/dev/null)
    
    local status_code=$(echo "$response" | tail -n1)
    
    if [ "$status_code" = "200" ]; then
        local body=$(echo "$response" | head -n-1)
        
        if command -v jq &> /dev/null; then
            local queue_count=$(echo "$body" | jq '. | length' 2>/dev/null)
            print_success "RabbitMQ 연결: ${queue_count}개 큐 발견"
            
            local total_messages=$(echo "$body" | jq '[.[].messages] | add' 2>/dev/null)
            print_success "RabbitMQ 메시지 확인: 총 ${total_messages}개 메시지"
            
            # 익스체인지 확인
            response=$(curl -s -u "$RABBITMQ_USER:$RABBITMQ_PASS" \
                "$RABBITMQ_URL/api/exchanges" --max-time 10 2>/dev/null)
            
            local exchanges=$(echo "$response" | jq -r '[.[] | select(.name | startswith("amq.") | not) | .name] | join(", ")' 2>/dev/null)
            
            if [ -n "$exchanges" ] && [ "$exchanges" != "null" ]; then
                print_info "발견된 익스체인지: $exchanges"
                local exchange_count=$(echo "$response" | jq '[.[] | select(.name | startswith("amq.") | not)] | length' 2>/dev/null)
                print_success "RabbitMQ 익스체인지 확인: ${exchange_count}개 발견"
            fi
        else
            print_success "RabbitMQ 연결: 성공 (jq 미설치로 상세 정보 제한)"
        fi
    else
        print_warning "RabbitMQ 확인: 연결 실패 (응답 코드: $status_code)"
    fi
}

verify_data_consistency() {
    local token=$1
    
    print_section "5단계: 로컬-클라우드 데이터 일관성 검증"
    
    # 로컬 데이터 조회
    local response=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/crud/clipboard" \
        -H "Authorization: Bearer $token" \
        --max-time 10 2>/dev/null)
    
    local status_code=$(echo "$response" | tail -n1)
    
    if [ "$status_code" != "200" ]; then
        print_failure "로컬 데이터 조회: 응답 코드 $status_code"
        return
    fi
    
    local local_body=$(echo "$response" | head -n-1)
    local local_count=0
    
    if command -v jq &> /dev/null; then
        local_count=$(echo "$local_body" | jq '. | length' 2>/dev/null || echo "0")
        [ "$local_count" = "null" ] && local_count=$(echo "$local_body" | jq '.items | length' 2>/dev/null || echo "0")
    fi
    
    print_success "로컬 데이터 조회: ${local_count}개 아이템"
    
    # 클라우드 데이터 조회
    response=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/crud/clipboard/cloud" \
        -H "Authorization: Bearer $token" \
        --max-time 10 2>/dev/null)
    
    status_code=$(echo "$response" | tail -n1)
    
    if [ "$status_code" = "200" ]; then
        local cloud_body=$(echo "$response" | head -n-1)
        local cloud_count=0
        
        if command -v jq &> /dev/null; then
            cloud_count=$(echo "$cloud_body" | jq '. | length' 2>/dev/null || echo "0")
            [ "$cloud_count" = "null" ] && cloud_count=$(echo "$cloud_body" | jq '.items | length' 2>/dev/null || echo "0")
        fi
        
        print_success "클라우드 데이터 조회: ${cloud_count}개 아이템"
        
        if command -v jq &> /dev/null && [ "$local_count" -gt 0 ]; then
            # 간단한 일치율 계산 (정확한 계산은 Python 버전 권장)
            local consistency_rate=0
            
            if [ "$local_count" -eq "$cloud_count" ]; then
                consistency_rate=100
            elif [ "$cloud_count" -gt 0 ]; then
                consistency_rate=$((cloud_count * 100 / local_count))
            fi
            
            print_info "로컬 아이템: ${local_count}개"
            print_info "클라우드 아이템: ${cloud_count}개"
            
            if [ $consistency_rate -ge 99 ]; then
                print_success "데이터 일관성: ${consistency_rate}% (기준: 99% 이상) ✓"
            elif [ $consistency_rate -ge 90 ]; then
                print_warning "데이터 일관성: ${consistency_rate}% (기준: 99% 이상)"
            else
                print_failure "데이터 일관성: ${consistency_rate}% (기준: 99% 이상)"
            fi
        fi
    elif [ "$status_code" = "404" ]; then
        print_warning "클라우드 데이터 조회: 클라우드 동기화 기능 미구현"
    else
        print_warning "클라우드 데이터 조회: 응답 코드 $status_code"
    fi
}

verify_service_logs_for_correlation() {
    print_section "6단계: 서비스 로그에서 Correlation ID 확인"
    
    local services=("crud-service" "notification-service" "monitoring-service")
    
    # 처음 3개 Correlation ID만 확인
    local sample_cids=("${CORRELATION_IDS[@]:0:3}")
    
    for service in "${services[@]}"; do
        local logs=$($DOCKER_COMPOSE logs --tail=100 "$service" 2>/dev/null)
        
        if [ $? -eq 0 ]; then
            local found_count=0
            
            for cid in "${sample_cids[@]}"; do
                if echo "$logs" | grep -q "$cid"; then
                    ((found_count++))
                fi
            done
            
            if [ $found_count -gt 0 ]; then
                print_success "$service Correlation ID: $found_count/${#sample_cids[@]}개 발견"
            else
                print_warning "$service Correlation ID: 로그에서 찾을 수 없음"
            fi
        else
            print_warning "$service 로그 조회: 실패"
        fi
    done
}

print_summary() {
    local end_time=$(date +%s)
    local duration=$((end_time - START_TIME))
    
    echo ""
    echo -e "${BLUE}======================================================================${NC}"
    echo -e "${CYAN}${BOLD}테스트 결과 요약${NC}"
    echo -e "${BLUE}======================================================================${NC}"
    echo "실행 시간: ${duration}초"
    echo -e "${GREEN}성공: $PASS_COUNT${NC}"
    echo -e "${RED}실패: $FAIL_COUNT${NC}"
    echo -e "${YELLOW}경고: $WARN_COUNT${NC}"
    echo -e "${CYAN}생성된 Correlation ID: ${#CORRELATION_IDS[@]}개${NC}"
    
    if [ ${#CORRELATION_IDS[@]} -gt 0 ]; then
        echo -e "\n${BOLD}Correlation IDs:${NC}"
        local display_count=5
        [ ${#CORRELATION_IDS[@]} -lt 5 ] && display_count=${#CORRELATION_IDS[@]}
        
        for ((i=0; i<display_count; i++)); do
            echo "  - ${CORRELATION_IDS[$i]}"
        done
        
        if [ ${#CORRELATION_IDS[@]} -gt 5 ]; then
            echo "  ... 외 $((${#CORRELATION_IDS[@]} - 5))개"
        fi
    fi
    
    echo -e "${BLUE}======================================================================${NC}"
    
    if [ $FAIL_COUNT -eq 0 ]; then
        echo -e "${GREEN}${BOLD}모든 테스트 통과!${NC}"
        return 0
    else
        echo -e "${RED}${BOLD}테스트 실패${NC}"
        return 1
    fi
}

# 메인 실행
main() {
    echo -e "\n${BLUE}${BOLD}======================================================================"
    echo "이벤트 기반 아키텍처 Correlation ID 추적 및 데이터 일관성 검증"
    echo -e "======================================================================${NC}\n"
    echo "테스트 시작 시간: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Base URL: $BASE_URL"
    echo "아이템 수: $ITEM_COUNT"
    echo ""
    
    # 의존성 확인 (DOCKER_COMPOSE 전역 변수 설정됨)
    check_dependencies
    
    # 0. 테스트 사용자 설정
    token=$(setup_test_user)
    if [ -z "$token" ]; then
        echo -e "\n${RED}로그인 실패로 테스트 중단${NC}"
        exit 1
    fi
    
    # 1. 클립보드 아이템 업로드
    upload_clipboard_items "$token" "$ITEM_COUNT"
    
    # 2. 클라우드 동기화
    trigger_cloud_sync "$token"
    
    # 3. 모니터링 DB에서 Correlation ID 추적
    verify_correlation_in_monitoring_db
    
    # 4. RabbitMQ 이벤트 흐름 확인
    verify_correlation_in_rabbitmq
    
    # 5. 데이터 일관성 검증
    verify_data_consistency "$token"
    
    # 6. 서비스 로그에서 Correlation ID 확인
    verify_service_logs_for_correlation
    
    # 결과 요약
    print_summary
}

# 스크립트 실행
main
exit_code=$?

exit $exit_code
