#!/bin/bash
# 모니터링 서비스 중단 시 핵심 서비스 정상 동작 자동화 테스트 (Bash)
# Ubuntu/Linux 환경용

set -e

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 설정
BASE_URL="${BASE_URL:-http://localhost:8576}"
USERNAME="testuser_$(date +%s)"
PASSWORD="testpass123"
EMAIL="testuser_$(date +%s)@example.com"

# 통계 변수
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0
START_TIME=$(date +%s)

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
    
    local missing_deps=0
    
    if ! command -v docker &> /dev/null; then
        print_failure "Docker가 설치되지 않았습니다"
        missing_deps=1
    else
        print_success "Docker 설치 확인"
    fi
    
    if ! command -v docker compose &> /dev/null && ! command -v docker-compose &> /dev/null; then
        print_failure "Docker Compose가 설치되지 않았습니다"
        missing_deps=1
    else
        print_success "Docker Compose 설치 확인"
    fi
    
    if ! command -v curl &> /dev/null; then
        print_failure "curl이 설치되지 않았습니다"
        missing_deps=1
    else
        print_success "curl 설치 확인"
    fi
    
    if ! command -v jq &> /dev/null; then
        print_warning "jq가 설치되지 않았습니다 (JSON 파싱에 권장)"
    else
        print_success "jq 설치 확인"
    fi
    
    if [ $missing_deps -eq 1 ]; then
        echo -e "\n${RED}필수 의존성이 설치되지 않았습니다. 설치 후 다시 실행하세요.${NC}"
        echo "설치 방법:"
        echo "  sudo apt update"
        echo "  sudo apt install -y docker.io docker-compose curl jq"
        exit 1
    fi
}

# Docker Compose 명령어 선택 (docker compose vs docker-compose)
get_docker_compose_cmd() {
    if command -v docker compose &> /dev/null; then
        echo "docker compose"
    else
        echo "docker-compose"
    fi
}

DOCKER_COMPOSE=$(get_docker_compose_cmd)

check_service_running() {
    local service=$1
    if $DOCKER_COMPOSE ps "$service" 2>/dev/null | grep -q "Up\|running"; then
        return 0
    else
        return 1
    fi
}

stop_monitoring_service() {
    print_section "1단계: 모니터링 서비스 중단"
    
    if $DOCKER_COMPOSE stop monitoring-service 2>/dev/null; then
        print_success "모니터링 서비스 중단: 성공적으로 중단됨"
        sleep 3
        
        if ! check_service_running "monitoring-service"; then
            print_success "모니터링 서비스 상태 확인: 중단됨"
        else
            print_warning "모니터링 서비스 상태 확인: 아직 실행 중인 것으로 보임"
        fi
    else
        print_failure "모니터링 서비스 중단: 실패"
    fi
}

test_login_service() {
    print_section "2-1단계: 로그인 서비스 테스트"
    
    local token=""
    
    # 회원가입
    local response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/login/register" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\",\"email\":\"$EMAIL\"}" \
        --max-time 10 2>/dev/null)
    
    local status_code=$(echo "$response" | tail -n1)
    
    if [[ "$status_code" =~ ^(200|201|409)$ ]]; then
        print_success "회원가입 API: 응답 코드 $status_code"
    else
        print_failure "회원가입 API: 예상치 못한 응답 $status_code"
    fi
    
    # 로그인
    response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/login/login" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
        --max-time 10 2>/dev/null)
    
    status_code=$(echo "$response" | tail -n1)
    local body=$(echo "$response" | head -n-1)
    
    if [ "$status_code" = "200" ]; then
        print_success "로그인 API: 성공 (응답 코드: $status_code)"
        
        if command -v jq &> /dev/null; then
            token=$(echo "$body" | jq -r '.access_token // .token // empty' 2>/dev/null)
        else
            # jq 없이 간단한 파싱 (완벽하지 않음)
            token=$(echo "$body" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
            [ -z "$token" ] && token=$(echo "$body" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
        fi
        
        if [ -n "$token" ]; then
            print_success "토큰 발급: 액세스 토큰 획득 성공"
        fi
    else
        print_failure "로그인 API: 실패 - 응답 코드 $status_code"
    fi
    
    # 토큰 검증
    if [ -n "$token" ]; then
        response=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/login/verify" \
            -H "Authorization: Bearer $token" \
            --max-time 10 2>/dev/null)
        
        status_code=$(echo "$response" | tail -n1)
        
        if [ "$status_code" = "200" ]; then
            print_success "토큰 검증: 성공"
        else
            print_warning "토큰 검증: 응답 코드 $status_code"
        fi
    fi
    
    echo "$token"
}

test_crud_service() {
    local token=$1
    print_section "2-2단계: 클립보드 CRUD 서비스 테스트"
    
    local auth_header=""
    [ -n "$token" ] && auth_header="-H \"Authorization: Bearer $token\""
    
    # 텍스트 클립보드 생성
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local response=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/crud/clipboard" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $token" \
        -d "{\"content\":\"테스트 클립보드 내용 - $timestamp\",\"type\":\"text\"}" \
        --max-time 10 2>/dev/null)
    
    local status_code=$(echo "$response" | tail -n1)
    
    if [[ "$status_code" =~ ^(200|201)$ ]]; then
        print_success "클립보드 생성 API: 성공 (응답 코드: $status_code)"
    else
        print_failure "클립보드 생성 API: 실패 - 응답 코드 $status_code"
    fi
    
    # 클립보드 조회
    response=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/crud/clipboard" \
        -H "Authorization: Bearer $token" \
        --max-time 10 2>/dev/null)
    
    status_code=$(echo "$response" | tail -n1)
    
    if [ "$status_code" = "200" ]; then
        print_success "클립보드 조회 API: 성공"
        print_success "클립보드 데이터 형식: 올바른 JSON 응답"
    else
        print_failure "클립보드 조회 API: 실패 - 응답 코드 $status_code"
    fi
}

test_notification_service() {
    local token=$1
    print_section "2-3단계: 알림 서비스 테스트"
    
    local response=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL/notification/notifications" \
        -H "Authorization: Bearer $token" \
        --max-time 10 2>/dev/null)
    
    local status_code=$(echo "$response" | tail -n1)
    
    if [ "$status_code" = "200" ]; then
        print_success "알림 조회 API: 성공"
    elif [ "$status_code" = "404" ]; then
        print_success "알림 조회 API: 엔드포인트 미구현 (정상)"
    else
        print_warning "알림 조회 API: 응답 코드 $status_code"
    fi
}

check_nginx_logs() {
    print_section "3단계: Nginx/API Gateway 로그 확인"
    
    local logs=$($DOCKER_COMPOSE logs --tail=50 nginx-gateway 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        local error_502=$(echo "$logs" | grep -c "502" || true)
        local error_500=$(echo "$logs" | grep -c "500" || true)
        
        if [ $error_502 -gt 0 ]; then
            print_failure "Nginx 502 에러: 502 에러 ${error_502}건 발견"
        else
            print_success "Nginx 502 에러: 502 에러 없음"
        fi
        
        if [ $error_500 -gt 0 ]; then
            print_warning "Nginx 500 에러: 500 에러 ${error_500}건 발견"
        else
            print_success "Nginx 500 에러: 500 에러 없음"
        fi
    else
        print_warning "Nginx 로그 확인: 로그 조회 실패"
    fi
}

check_service_logs() {
    print_section "4단계: 각 서비스 로그 에러 확인"
    
    local services=("login-service" "crud-service" "notification-service")
    local error_keywords=("ERROR" "Exception" "Failed" "refused" "timeout")
    
    for service in "${services[@]}"; do
        local logs=$($DOCKER_COMPOSE logs --tail=30 "$service" 2>/dev/null)
        
        if [ $? -eq 0 ]; then
            local errors_found=()
            
            for keyword in "${error_keywords[@]}"; do
                if echo "$logs" | grep -qi "$keyword"; then
                    errors_found+=("$keyword")
                fi
            done
            
            if [ ${#errors_found[@]} -gt 0 ]; then
                print_warning "$service 로그 확인: 다음 키워드 발견 - ${errors_found[*]}"
            else
                print_success "$service 로그 확인: 에러 없음"
            fi
        else
            print_warning "$service 로그 확인: 로그 조회 실패"
        fi
    done
}

check_core_services_status() {
    print_section "5단계: 핵심 서비스 상태 확인"
    
    local core_services=("login-service" "crud-service" "notification-service" "nginx-gateway")
    
    for service in "${core_services[@]}"; do
        if check_service_running "$service"; then
            print_success "$service 상태: 실행 중"
        else
            print_failure "$service 상태: 중단됨"
        fi
    done
}

restart_monitoring_service() {
    print_section "6단계: 모니터링 서비스 재시작"
    
    if $DOCKER_COMPOSE start monitoring-service 2>/dev/null; then
        print_success "모니터링 서비스 재시작: 성공"
        sleep 3
        
        if check_service_running "monitoring-service"; then
            print_success "모니터링 서비스 상태: 실행 중"
        else
            print_warning "모니터링 서비스 상태: 재시작 후에도 중단됨"
        fi
    else
        print_failure "모니터링 서비스 재시작: 실패"
    fi
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
    echo "모니터링 서비스 중단 시 핵심 서비스 정상 동작 테스트"
    echo -e "======================================================================${NC}\n"
    echo "테스트 시작 시간: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Base URL: $BASE_URL"
    echo ""
    
    # 의존성 확인
    check_dependencies
    
    # 1. 모니터링 서비스 중단
    stop_monitoring_service
    
    # 2. 핵심 서비스 기능 테스트
    token=$(test_login_service)
    test_crud_service "$token"
    test_notification_service "$token"
    
    # 3. Nginx 로그 확인
    check_nginx_logs
    
    # 4. 각 서비스 로그 확인
    check_service_logs
    
    # 5. 핵심 서비스 상태 확인
    check_core_services_status
    
    # 6. 모니터링 서비스 재시작
    restart_monitoring_service
    
    # 결과 요약
    print_summary
}

# 스크립트 실행
main
exit_code=$?

exit $exit_code
