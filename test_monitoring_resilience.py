#!/usr/bin/env python3
"""
모니터링 서비스 중단 시 핵심 서비스 정상 동작 자동화 테스트

목표: 모니터링 서비스가 중단되어도 로그인/클립보드/알림 등 핵심 기능이 정상 동작하는지 확인
"""

import subprocess
import time
import requests
import sys
import json
from datetime import datetime
from typing import Dict, List, Tuple

# 테스트 설정
BASE_URL = "http://localhost:8576"
LOGIN_API = f"{BASE_URL}/login"
CRUD_API = f"{BASE_URL}/crud"
NOTIFICATION_API = f"{BASE_URL}/notification"

# 테스트 계정 정보 (환경에 맞게 수정)
TEST_USER = {
    "username": "testuser",
    "password": "testpass123",
    "email": "test@example.com"
}

# 색상 출력을 위한 ANSI 코드
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
        self.start_time = datetime.now()
    
    def add_pass(self, test_name: str, message: str = ""):
        self.passed.append((test_name, message))
        print(f"{Colors.GREEN}✓{Colors.RESET} {test_name}: {message}")
    
    def add_fail(self, test_name: str, message: str = ""):
        self.failed.append((test_name, message))
        print(f"{Colors.RED}✗{Colors.RESET} {test_name}: {message}")
    
    def add_warning(self, test_name: str, message: str = ""):
        self.warnings.append((test_name, message))
        print(f"{Colors.YELLOW}⚠{Colors.RESET} {test_name}: {message}")
    
    def print_summary(self):
        print("\n" + "="*70)
        print(f"{Colors.BOLD}테스트 결과 요약{Colors.RESET}")
        print("="*70)
        print(f"실행 시간: {datetime.now() - self.start_time}")
        print(f"{Colors.GREEN}성공: {len(self.passed)}{Colors.RESET}")
        print(f"{Colors.RED}실패: {len(self.failed)}{Colors.RESET}")
        print(f"{Colors.YELLOW}경고: {len(self.warnings)}{Colors.RESET}")
        
        if self.failed:
            print(f"\n{Colors.RED}실패한 테스트:{Colors.RESET}")
            for name, msg in self.failed:
                print(f"  - {name}: {msg}")
        
        if self.warnings:
            print(f"\n{Colors.YELLOW}경고:{Colors.RESET}")
            for name, msg in self.warnings:
                print(f"  - {name}: {msg}")
        
        print("="*70)
        
        if self.failed:
            print(f"{Colors.RED}테스트 실패{Colors.RESET}")
            return False
        else:
            print(f"{Colors.GREEN}모든 테스트 통과!{Colors.RESET}")
            return True


def run_command(cmd: str, shell=True) -> Tuple[int, str, str]:
    """명령어 실행 및 결과 반환"""
    result = subprocess.run(
        cmd,
        shell=shell,
        capture_output=True,
        text=True,
        timeout=30
    )
    return result.returncode, result.stdout, result.stderr


def check_service_running(service_name: str) -> bool:
    """서비스가 실행 중인지 확인"""
    returncode, stdout, _ = run_command(f"docker compose ps {service_name}")
    return "Up" in stdout or "running" in stdout.lower()


def stop_monitoring_service(result: TestResult):
    """모니터링 서비스 중단"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}1단계: 모니터링 서비스 중단{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    returncode, stdout, stderr = run_command("docker compose stop monitoring-service")
    
    if returncode == 0:
        result.add_pass("모니터링 서비스 중단", "성공적으로 중단됨")
        time.sleep(3)  # 서비스가 완전히 중단될 때까지 대기
        
        # 중단 확인
        if not check_service_running("monitoring-service"):
            result.add_pass("모니터링 서비스 상태 확인", "중단됨")
        else:
            result.add_warning("모니터링 서비스 상태 확인", "아직 실행 중인 것으로 보임")
    else:
        result.add_fail("모니터링 서비스 중단", f"실패: {stderr}")


def test_login_service(result: TestResult) -> str:
    """로그인 서비스 테스트"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}2-1단계: 로그인 서비스 테스트{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    token = None
    
    # 회원가입 테스트
    try:
        response = requests.post(
            f"{LOGIN_API}/register",
            json=TEST_USER,
            timeout=10
        )
        
        if response.status_code in [200, 201, 409]:  # 409는 이미 존재하는 계정
            result.add_pass("회원가입 API", f"응답 코드: {response.status_code}")
        else:
            result.add_fail("회원가입 API", f"예상치 못한 응답: {response.status_code}")
    except requests.exceptions.RequestException as e:
        result.add_fail("회원가입 API", f"요청 실패: {str(e)}")
    
    # 로그인 테스트
    try:
        response = requests.post(
            f"{LOGIN_API}/login",
            json={
                "username": TEST_USER["username"],
                "password": TEST_USER["password"]
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result.add_pass("로그인 API", f"성공 (응답 코드: {response.status_code})")
            data = response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                result.add_pass("토큰 발급", "액세스 토큰 획득 성공")
        else:
            result.add_fail("로그인 API", f"실패: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        result.add_fail("로그인 API", f"요청 실패: {str(e)}")
    
    # 토큰 검증 테스트
    if token:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(
                f"{LOGIN_API}/verify",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result.add_pass("토큰 검증", "성공")
            else:
                result.add_warning("토큰 검증", f"응답 코드: {response.status_code}")
        except requests.exceptions.RequestException as e:
            result.add_warning("토큰 검증", f"요청 실패: {str(e)}")
    
    return token


def test_crud_service(result: TestResult, token: str):
    """클립보드 CRUD 서비스 테스트"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}2-2단계: 클립보드 CRUD 서비스 테스트{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    # 텍스트 클립보드 생성 테스트
    test_content = f"테스트 클립보드 내용 - {datetime.now()}"
    clipboard_id = None
    
    try:
        response = requests.post(
            f"{CRUD_API}/clipboard",
            json={
                "content": test_content,
                "type": "text"
            },
            headers=headers,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            result.add_pass("클립보드 생성 API", f"성공 (응답 코드: {response.status_code})")
            data = response.json()
            clipboard_id = data.get("id") or data.get("clipboard_id")
        else:
            result.add_fail("클립보드 생성 API", f"실패: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        result.add_fail("클립보드 생성 API", f"요청 실패: {str(e)}")
    
    # 클립보드 조회 테스트
    try:
        response = requests.get(
            f"{CRUD_API}/clipboard",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            result.add_pass("클립보드 조회 API", "성공")
            data = response.json()
            if isinstance(data, list) or isinstance(data, dict):
                result.add_pass("클립보드 데이터 형식", "올바른 JSON 응답")
        else:
            result.add_fail("클립보드 조회 API", f"실패: {response.status_code}")
    except requests.exceptions.RequestException as e:
        result.add_fail("클립보드 조회 API", f"요청 실패: {str(e)}")
    
    # 특정 클립보드 조회 테스트
    if clipboard_id:
        try:
            response = requests.get(
                f"{CRUD_API}/clipboard/{clipboard_id}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                result.add_pass("특정 클립보드 조회", "성공")
            else:
                result.add_warning("특정 클립보드 조회", f"응답 코드: {response.status_code}")
        except requests.exceptions.RequestException as e:
            result.add_warning("특정 클립보드 조회", f"요청 실패: {str(e)}")
    
    # 클립보드 업데이트 테스트
    if clipboard_id:
        try:
            response = requests.put(
                f"{CRUD_API}/clipboard/{clipboard_id}",
                json={"content": f"수정된 내용 - {datetime.now()}"},
                headers=headers,
                timeout=10
            )
            
            if response.status_code in [200, 204]:
                result.add_pass("클립보드 수정 API", "성공")
            else:
                result.add_warning("클립보드 수정 API", f"응답 코드: {response.status_code}")
        except requests.exceptions.RequestException as e:
            result.add_warning("클립보드 수정 API", f"요청 실패: {str(e)}")


def test_notification_service(result: TestResult, token: str):
    """알림 서비스 테스트"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}2-3단계: 알림 서비스 테스트{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    # 알림 조회 테스트
    try:
        response = requests.get(
            f"{NOTIFICATION_API}/notifications",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            result.add_pass("알림 조회 API", "성공")
        elif response.status_code == 404:
            result.add_pass("알림 조회 API", "엔드포인트 미구현 (정상)")
        else:
            result.add_warning("알림 조회 API", f"응답 코드: {response.status_code}")
    except requests.exceptions.RequestException as e:
        result.add_warning("알림 조회 API", f"요청 실패: {str(e)}")


def check_nginx_logs(result: TestResult):
    """Nginx 로그 확인 - 502 에러 체크"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}3단계: Nginx/API Gateway 로그 확인{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    returncode, stdout, stderr = run_command(
        "docker compose logs --tail=50 nginx-gateway"
    )
    
    if returncode == 0:
        # 502 Bad Gateway 에러 확인
        error_count_502 = stdout.count("502")
        error_count_500 = stdout.count("500")
        
        if error_count_502 > 0:
            result.add_fail("Nginx 502 에러", f"502 에러 {error_count_502}건 발견")
        else:
            result.add_pass("Nginx 502 에러", "502 에러 없음")
        
        if error_count_500 > 0:
            result.add_warning("Nginx 500 에러", f"500 에러 {error_count_500}건 발견")
        else:
            result.add_pass("Nginx 500 에러", "500 에러 없음")
    else:
        result.add_warning("Nginx 로그 확인", "로그 조회 실패")


def check_service_logs(result: TestResult):
    """각 서비스 로그에서 에러 확인"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}4단계: 각 서비스 로그 에러 확인{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    services = ["login-service", "crud-service", "notification-service"]
    
    for service in services:
        returncode, stdout, stderr = run_command(
            f"docker compose logs --tail=30 {service}"
        )
        
        if returncode == 0:
            # 일반적인 에러 키워드 확인
            error_keywords = ["ERROR", "Exception", "Failed", "refused", "timeout"]
            errors_found = []
            
            for keyword in error_keywords:
                if keyword.lower() in stdout.lower():
                    errors_found.append(keyword)
            
            if errors_found:
                result.add_warning(
                    f"{service} 로그 확인",
                    f"다음 키워드 발견: {', '.join(errors_found)}"
                )
            else:
                result.add_pass(f"{service} 로그 확인", "에러 없음")
        else:
            result.add_warning(f"{service} 로그 확인", "로그 조회 실패")


def check_core_services_running(result: TestResult):
    """핵심 서비스들이 실행 중인지 확인"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}5단계: 핵심 서비스 상태 확인{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    core_services = [
        "login-service",
        "crud-service",
        "notification-service",
        "nginx-gateway"
    ]
    
    for service in core_services:
        if check_service_running(service):
            result.add_pass(f"{service} 상태", "실행 중")
        else:
            result.add_fail(f"{service} 상태", "중단됨")


def restart_monitoring_service(result: TestResult):
    """모니터링 서비스 재시작"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}6단계: 모니터링 서비스 재시작{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    returncode, stdout, stderr = run_command("docker compose start monitoring-service")
    
    if returncode == 0:
        result.add_pass("모니터링 서비스 재시작", "성공")
        time.sleep(3)
        
        if check_service_running("monitoring-service"):
            result.add_pass("모니터링 서비스 상태", "실행 중")
        else:
            result.add_warning("모니터링 서비스 상태", "재시작 후에도 중단됨")
    else:
        result.add_fail("모니터링 서비스 재시작", f"실패: {stderr}")


def main():
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("="*70)
    print("모니터링 서비스 중단 시 핵심 서비스 정상 동작 테스트")
    print("="*70)
    print(f"{Colors.RESET}\n")
    print(f"테스트 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL: {BASE_URL}\n")
    
    result = TestResult()
    
    try:
        # 1. 모니터링 서비스 중단
        stop_monitoring_service(result)
        
        # 2. 핵심 서비스 기능 테스트
        token = test_login_service(result)
        test_crud_service(result, token)
        test_notification_service(result, token)
        
        # 3. Nginx 로그 확인
        check_nginx_logs(result)
        
        # 4. 각 서비스 로그 확인
        check_service_logs(result)
        
        # 5. 핵심 서비스 상태 확인
        check_core_services_running(result)
        
        # 6. 모니터링 서비스 재시작
        restart_monitoring_service(result)
        
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}테스트 중단됨{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}예상치 못한 에러: {str(e)}{Colors.RESET}")
        sys.exit(1)
    
    # 결과 요약 출력
    success = result.print_summary()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
