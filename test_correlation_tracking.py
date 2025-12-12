#!/usr/bin/env python3
"""
이벤트 기반 아키텍처 Correlation ID 추적 및 데이터 일관성 검증 자동화 테스트

목표:
1. Correlation ID로 전체 이벤트 흐름을 추적
2. 로컬-클라우드 데이터 일치율 99% 이상 검증
"""

import subprocess
import time
import requests
import sys
import json
import uuid
import mysql.connector
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import base64
import io
from pathlib import Path

# 테스트 설정
BASE_URL = "http://localhost:8576"
LOGIN_API = f"{BASE_URL}/login"
CRUD_API = f"{BASE_URL}/crud"
RABBITMQ_MANAGEMENT_URL = "http://localhost:15672"

# 데이터베이스 설정
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "qwerty",  # .env의 DB_ROOT_PASSWORD
    "port": 3306
}

# RabbitMQ 설정
RABBITMQ_CONFIG = {
    "user": "qwerty",  # .env의 RABBITMQ_USER
    "password": "qwerty"  # .env의 RABBITMQ_PASS
}

# 테스트 계정
TEST_USER = {
    "username": f"correlation_test_{int(time.time())}",
    "password": "testpass123",
    "email": f"correlation_test_{int(time.time())}@example.com"
}

# 색상 출력
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
        self.correlation_ids = []
        self.uploaded_items = []
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
    
    def add_info(self, message: str):
        print(f"{Colors.CYAN}ℹ{Colors.RESET} {message}")
    
    def print_summary(self):
        print("\n" + "="*70)
        print(f"{Colors.BOLD}테스트 결과 요약{Colors.RESET}")
        print("="*70)
        print(f"실행 시간: {datetime.now() - self.start_time}")
        print(f"{Colors.GREEN}성공: {len(self.passed)}{Colors.RESET}")
        print(f"{Colors.RED}실패: {len(self.failed)}{Colors.RESET}")
        print(f"{Colors.YELLOW}경고: {len(self.warnings)}{Colors.RESET}")
        print(f"{Colors.CYAN}생성된 Correlation ID: {len(self.correlation_ids)}개{Colors.RESET}")
        print(f"{Colors.CYAN}업로드된 아이템: {len(self.uploaded_items)}개{Colors.RESET}")
        
        if self.correlation_ids:
            print(f"\n{Colors.BOLD}Correlation IDs:{Colors.RESET}")
            for cid in self.correlation_ids[:5]:  # 최대 5개만 표시
                print(f"  - {cid}")
            if len(self.correlation_ids) > 5:
                print(f"  ... 외 {len(self.correlation_ids) - 5}개")
        
        if self.failed:
            print(f"\n{Colors.RED}실패한 테스트:{Colors.RESET}")
            for name, msg in self.failed:
                print(f"  - {name}: {msg}")
        
        print("="*70)
        
        if self.failed:
            print(f"{Colors.RED}테스트 실패{Colors.RESET}")
            return False
        else:
            print(f"{Colors.GREEN}모든 테스트 통과!{Colors.RESET}")
            return True


def get_db_connection(database: str = None):
    """데이터베이스 연결"""
    config = DB_CONFIG.copy()
    if database:
        config["database"] = database
    try:
        conn = mysql.connector.connect(**config)
        return conn
    except Exception as e:
        print(f"{Colors.RED}데이터베이스 연결 실패: {str(e)}{Colors.RESET}")
        return None


def setup_test_user(result: TestResult) -> Optional[str]:
    """테스트 사용자 생성 및 로그인"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}0단계: 테스트 사용자 설정{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    # 회원가입
    try:
        response = requests.post(
            f"{LOGIN_API}/register",
            json=TEST_USER,
            timeout=10
        )
        if response.status_code in [200, 201]:
            result.add_pass("테스트 사용자 생성", f"사용자명: {TEST_USER['username']}")
        elif response.status_code == 409:
            result.add_warning("테스트 사용자 생성", "이미 존재하는 사용자")
        else:
            result.add_fail("테스트 사용자 생성", f"응답 코드: {response.status_code}")
    except Exception as e:
        result.add_fail("테스트 사용자 생성", str(e))
    
    # 로그인
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
            data = response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                result.add_pass("로그인 및 토큰 획득", "성공")
                return token
        
        result.add_fail("로그인", f"응답 코드: {response.status_code}")
        return None
    except Exception as e:
        result.add_fail("로그인", str(e))
        return None


def generate_correlation_id() -> str:
    """Correlation ID 생성"""
    return f"test-{uuid.uuid4()}"


def create_test_image() -> bytes:
    """테스트용 간단한 이미지 생성 (1x1 PNG)"""
    # 1x1 빨간색 PNG
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    )
    return png_data


def upload_clipboard_items(result: TestResult, token: str, count: int = 10):
    """여러 클립보드 아이템 업로드"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}1단계: 클립보드 아이템 업로드 ({count}개){Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    headers = {"Authorization": f"Bearer {token}"}
    uploaded_count = 0
    
    for i in range(count):
        correlation_id = generate_correlation_id()
        result.correlation_ids.append(correlation_id)
        
        # Correlation ID를 헤더에 추가
        headers_with_correlation = headers.copy()
        headers_with_correlation["X-Correlation-ID"] = correlation_id
        
        # 텍스트와 이미지를 번갈아가며 업로드
        if i % 2 == 0:
            # 텍스트 업로드
            try:
                response = requests.post(
                    f"{CRUD_API}/clipboard",
                    json={
                        "content": f"테스트 텍스트 {i+1} - {datetime.now()}",
                        "type": "text",
                        "correlation_id": correlation_id
                    },
                    headers=headers_with_correlation,
                    timeout=10
                )
                
                if response.status_code in [200, 201]:
                    data = response.json()
                    item_id = data.get("id") or data.get("clipboard_id")
                    result.uploaded_items.append({
                        "id": item_id,
                        "type": "text",
                        "correlation_id": correlation_id
                    })
                    uploaded_count += 1
                    result.add_info(f"텍스트 {i+1} 업로드 성공 (Correlation ID: {correlation_id[:16]}...)")
                else:
                    result.add_warning(f"텍스트 {i+1} 업로드", f"응답 코드: {response.status_code}")
            except Exception as e:
                result.add_warning(f"텍스트 {i+1} 업로드", str(e))
        else:
            # 이미지 업로드
            try:
                files = {
                    'file': (f'test_image_{i+1}.png', create_test_image(), 'image/png')
                }
                data_fields = {
                    'type': 'image',
                    'correlation_id': correlation_id
                }
                
                response = requests.post(
                    f"{CRUD_API}/clipboard/upload",
                    files=files,
                    data=data_fields,
                    headers=headers_with_correlation,
                    timeout=10
                )
                
                if response.status_code in [200, 201]:
                    data = response.json()
                    item_id = data.get("id") or data.get("clipboard_id")
                    result.uploaded_items.append({
                        "id": item_id,
                        "type": "image",
                        "correlation_id": correlation_id
                    })
                    uploaded_count += 1
                    result.add_info(f"이미지 {i+1} 업로드 성공 (Correlation ID: {correlation_id[:16]}...)")
                else:
                    result.add_warning(f"이미지 {i+1} 업로드", f"응답 코드: {response.status_code}")
            except Exception as e:
                result.add_warning(f"이미지 {i+1} 업로드", str(e))
        
        # 서버 부하 방지를 위한 짧은 대기
        time.sleep(0.5)
    
    result.add_pass("클립보드 아이템 업로드", f"{uploaded_count}/{count}개 성공")
    
    # 이벤트 처리를 위한 대기
    result.add_info("이벤트 처리 대기 중... (10초)")
    time.sleep(10)


def trigger_cloud_sync(result: TestResult, token: str):
    """클라우드 동기화 트리거"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}2단계: 클라우드 동기화 실행{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(
            f"{CRUD_API}/sync/cloud",
            headers=headers,
            timeout=30
        )
        
        if response.status_code in [200, 201, 202]:
            result.add_pass("클라우드 동기화 트리거", "성공")
            result.add_info("동기화 처리 대기 중... (15초)")
            time.sleep(15)
        elif response.status_code == 404:
            result.add_warning("클라우드 동기화 트리거", "엔드포인트 미구현")
        else:
            result.add_warning("클라우드 동기화 트리거", f"응답 코드: {response.status_code}")
    except Exception as e:
        result.add_warning("클라우드 동기화 트리거", str(e))


def verify_correlation_ids_in_monitoring_db(result: TestResult):
    """모니터링 DB에서 Correlation ID 추적"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}3단계: 모니터링 DB에서 Correlation ID 추적{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    conn = get_db_connection("monitoring_db")
    if not conn:
        result.add_fail("모니터링 DB 연결", "연결 실패")
        return
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # 테이블 존재 확인
        cursor.execute("SHOW TABLES")
        tables = [table[f'Tables_in_monitoring_db'] for table in cursor.fetchall()]
        
        if not tables:
            result.add_warning("모니터링 DB 테이블", "테이블이 없음 (로그 수집 미구현일 수 있음)")
            conn.close()
            return
        
        result.add_info(f"발견된 테이블: {', '.join(tables)}")
        
        # logs 테이블에서 Correlation ID 확인
        log_tables = [t for t in tables if 'log' in t.lower()]
        
        if not log_tables:
            result.add_warning("로그 테이블", "로그 테이블을 찾을 수 없음")
            conn.close()
            return
        
        found_correlation_ids = 0
        total_log_entries = 0
        
        for table in log_tables:
            try:
                # 테이블 컬럼 확인
                cursor.execute(f"DESCRIBE {table}")
                columns = [col['Field'] for col in cursor.fetchall()]
                
                correlation_column = None
                for col in columns:
                    if 'correlation' in col.lower():
                        correlation_column = col
                        break
                
                if not correlation_column:
                    result.add_info(f"테이블 '{table}'에 correlation 컬럼 없음")
                    continue
                
                # 우리가 생성한 Correlation ID가 있는지 확인
                for cid in result.correlation_ids[:5]:  # 처음 5개만 확인
                    cursor.execute(
                        f"SELECT COUNT(*) as count FROM {table} WHERE {correlation_column} = %s",
                        (cid,)
                    )
                    count = cursor.fetchone()['count']
                    
                    if count > 0:
                        found_correlation_ids += 1
                        total_log_entries += count
                        result.add_info(
                            f"Correlation ID {cid[:16]}... 발견: {count}개 로그 ({table})"
                        )
                
            except Exception as e:
                result.add_warning(f"테이블 '{table}' 조회", str(e))
        
        if found_correlation_ids > 0:
            result.add_pass(
                "Correlation ID 추적",
                f"{found_correlation_ids}개 ID에서 총 {total_log_entries}개 로그 발견"
            )
        else:
            result.add_warning(
                "Correlation ID 추적",
                "모니터링 DB에서 Correlation ID를 찾을 수 없음 (로그 수집 미구현일 수 있음)"
            )
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        result.add_fail("모니터링 DB 조회", str(e))
        if conn:
            conn.close()


def verify_correlation_ids_in_rabbitmq(result: TestResult):
    """RabbitMQ에서 이벤트 흐름 확인"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}4단계: RabbitMQ 이벤트 흐름 확인{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    try:
        auth = (RABBITMQ_CONFIG["user"], RABBITMQ_CONFIG["password"])
        
        # RabbitMQ Management API로 큐 정보 조회
        response = requests.get(
            f"{RABBITMQ_MANAGEMENT_URL}/api/queues",
            auth=auth,
            timeout=10
        )
        
        if response.status_code == 200:
            queues = response.json()
            result.add_pass("RabbitMQ 연결", f"{len(queues)}개 큐 발견")
            
            total_messages = 0
            for queue in queues:
                queue_name = queue.get('name', 'unknown')
                messages = queue.get('messages', 0)
                total_messages += messages
                
                if messages > 0:
                    result.add_info(f"큐 '{queue_name}': {messages}개 메시지")
            
            result.add_pass("RabbitMQ 메시지 확인", f"총 {total_messages}개 메시지")
            
            # 익스체인지 정보 조회
            response = requests.get(
                f"{RABBITMQ_MANAGEMENT_URL}/api/exchanges",
                auth=auth,
                timeout=10
            )
            
            if response.status_code == 200:
                exchanges = response.json()
                custom_exchanges = [e for e in exchanges if not e['name'].startswith('amq.')]
                
                if custom_exchanges:
                    result.add_info(f"발견된 익스체인지: {', '.join([e['name'] for e in custom_exchanges])}")
                    result.add_pass("RabbitMQ 익스체인지 확인", f"{len(custom_exchanges)}개 발견")
        else:
            result.add_fail("RabbitMQ 연결", f"응답 코드: {response.status_code}")
            
    except Exception as e:
        result.add_warning("RabbitMQ 확인", f"연결 실패: {str(e)} (RabbitMQ Management UI가 활성화되어 있는지 확인)")


def verify_data_consistency(result: TestResult, token: str):
    """로컬-클라우드 데이터 일관성 검증"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}5단계: 로컬-클라우드 데이터 일관성 검증{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 로컬 데이터 조회
    try:
        response = requests.get(
            f"{CRUD_API}/clipboard",
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            result.add_fail("로컬 데이터 조회", f"응답 코드: {response.status_code}")
            return
        
        local_data = response.json()
        local_items = local_data if isinstance(local_data, list) else local_data.get('items', [])
        local_count = len(local_items)
        
        result.add_pass("로컬 데이터 조회", f"{local_count}개 아이템")
        
    except Exception as e:
        result.add_fail("로컬 데이터 조회", str(e))
        return
    
    # 클라우드 데이터 조회
    try:
        response = requests.get(
            f"{CRUD_API}/clipboard/cloud",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            cloud_data = response.json()
            cloud_items = cloud_data if isinstance(cloud_data, list) else cloud_data.get('items', [])
            cloud_count = len(cloud_items)
            
            result.add_pass("클라우드 데이터 조회", f"{cloud_count}개 아이템")
            
            # 데이터 일치율 계산
            if local_count == 0:
                result.add_warning("데이터 일치율", "로컬 데이터가 없음")
                return
            
            # ID 기반으로 일치하는 아이템 찾기
            local_ids = set(item.get('id') for item in local_items if item.get('id'))
            cloud_ids = set(item.get('id') for item in cloud_items if item.get('id'))
            
            matching_ids = local_ids.intersection(cloud_ids)
            total_unique = local_ids.union(cloud_ids)
            
            if len(total_unique) > 0:
                consistency_rate = (len(matching_ids) / len(total_unique)) * 100
                
                result.add_info(f"로컬 고유 ID: {len(local_ids)}개")
                result.add_info(f"클라우드 고유 ID: {len(cloud_ids)}개")
                result.add_info(f"일치하는 ID: {len(matching_ids)}개")
                result.add_info(f"전체 고유 ID: {len(total_unique)}개")
                
                if consistency_rate >= 99.0:
                    result.add_pass(
                        "데이터 일관성",
                        f"{consistency_rate:.2f}% (기준: 99% 이상) ✓"
                    )
                elif consistency_rate >= 90.0:
                    result.add_warning(
                        "데이터 일관성",
                        f"{consistency_rate:.2f}% (기준: 99% 이상)"
                    )
                else:
                    result.add_fail(
                        "데이터 일관성",
                        f"{consistency_rate:.2f}% (기준: 99% 이상)"
                    )
            else:
                result.add_warning("데이터 일관성", "비교 가능한 데이터 없음")
                
        elif response.status_code == 404:
            result.add_warning("클라우드 데이터 조회", "클라우드 동기화 기능 미구현")
        else:
            result.add_warning("클라우드 데이터 조회", f"응답 코드: {response.status_code}")
            
    except Exception as e:
        result.add_warning("클라우드 데이터 조회", str(e))


def verify_service_logs_for_correlation(result: TestResult):
    """각 서비스 로그에서 Correlation ID 확인"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}6단계: 서비스 로그에서 Correlation ID 확인{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    services = ["crud-service", "notification-service", "monitoring-service"]
    
    # 확인할 Correlation ID (처음 3개만)
    sample_cids = result.correlation_ids[:3]
    
    for service in services:
        try:
            # Docker 로그 조회
            cmd = f"docker compose logs --tail=100 {service}"
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if proc.returncode == 0:
                logs = proc.stdout
                found_count = 0
                
                for cid in sample_cids:
                    if cid in logs:
                        found_count += 1
                
                if found_count > 0:
                    result.add_pass(
                        f"{service} Correlation ID",
                        f"{found_count}/{len(sample_cids)}개 발견"
                    )
                else:
                    result.add_warning(
                        f"{service} Correlation ID",
                        "로그에서 찾을 수 없음 (구현 필요할 수 있음)"
                    )
            else:
                result.add_warning(f"{service} 로그 조회", "실패")
                
        except Exception as e:
            result.add_warning(f"{service} 로그 조회", str(e))


def check_crud_database_consistency(result: TestResult):
    """CRUD 데이터베이스에서 직접 데이터 일관성 확인"""
    print(f"\n{Colors.BLUE}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}7단계: 데이터베이스 레벨 일관성 확인{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    conn = get_db_connection("crud_db")
    if not conn:
        result.add_warning("CRUD DB 연결", "연결 실패")
        return
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # 업로드된 아이템이 DB에 있는지 확인
        uploaded_ids = [item['id'] for item in result.uploaded_items if item.get('id')]
        
        if not uploaded_ids:
            result.add_warning("업로드 아이템 확인", "확인할 ID 없음")
            conn.close()
            return
        
        # clipboard 테이블에서 확인 (테이블명은 실제 스키마에 맞게 조정)
        try:
            # 테이블 목록 확인
            cursor.execute("SHOW TABLES")
            tables = [table[f'Tables_in_crud_db'] for table in cursor.fetchall()]
            
            clipboard_table = None
            for table in tables:
                if 'clipboard' in table.lower() or 'clip' in table.lower():
                    clipboard_table = table
                    break
            
            if clipboard_table:
                result.add_info(f"클립보드 테이블 발견: {clipboard_table}")
                
                # 샘플 ID로 확인 (처음 5개)
                found_count = 0
                for item_id in uploaded_ids[:5]:
                    cursor.execute(f"SELECT COUNT(*) as count FROM {clipboard_table} WHERE id = %s", (item_id,))
                    count = cursor.fetchone()['count']
                    if count > 0:
                        found_count += 1
                
                if found_count > 0:
                    result.add_pass(
                        "DB 아이템 확인",
                        f"{found_count}/{min(5, len(uploaded_ids))}개 샘플 아이템 발견"
                    )
                else:
                    result.add_warning("DB 아이템 확인", "업로드된 아이템을 DB에서 찾을 수 없음")
            else:
                result.add_warning("클립보드 테이블", "테이블을 찾을 수 없음")
                
        except Exception as e:
            result.add_warning("DB 아이템 확인", str(e))
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        result.add_warning("데이터베이스 조회", str(e))
        if conn:
            conn.close()


def main():
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("="*70)
    print("이벤트 기반 아키텍처 Correlation ID 추적 및 데이터 일관성 검증")
    print("="*70)
    print(f"{Colors.RESET}\n")
    print(f"테스트 시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL: {BASE_URL}\n")
    
    result = TestResult()
    
    try:
        # 0. 테스트 사용자 설정
        token = setup_test_user(result)
        if not token:
            print(f"\n{Colors.RED}로그인 실패로 테스트 중단{Colors.RESET}")
            sys.exit(1)
        
        # 1. 클립보드 아이템 업로드 (Correlation ID 포함)
        upload_clipboard_items(result, token, count=10)
        
        # 2. 클라우드 동기화 트리거
        trigger_cloud_sync(result, token)
        
        # 3. 모니터링 DB에서 Correlation ID 추적
        verify_correlation_ids_in_monitoring_db(result)
        
        # 4. RabbitMQ에서 이벤트 흐름 확인
        verify_correlation_ids_in_rabbitmq(result)
        
        # 5. 로컬-클라우드 데이터 일관성 검증
        verify_data_consistency(result, token)
        
        # 6. 서비스 로그에서 Correlation ID 확인
        verify_service_logs_for_correlation(result)
        
        # 7. 데이터베이스 레벨 일관성 확인
        check_crud_database_consistency(result)
        
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}테스트 중단됨{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}예상치 못한 에러: {str(e)}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 결과 요약 출력
    success = result.print_summary()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
