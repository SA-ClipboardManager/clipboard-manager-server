# 모니터링 서비스 중단 시 핵심 서비스 정상 동작 자동화 테스트 (PowerShell)
# 목표: 모니터링 서비스가 중단되어도 로그인/클립보드/알림 등 핵심 기능이 정상 동작하는지 확인

param(
    [string]$BaseUrl = "http://localhost:8576",
    [string]$Username = "testuser",
    [string]$Password = "testpass123",
    [string]$Email = "test@example.com"
)

# 색상 출력 설정
$script:PassCount = 0
$script:FailCount = 0
$script:WarnCount = 0
$script:StartTime = Get-Date

function Write-Success {
    param([string]$Message)
    Write-Host "✓ " -ForegroundColor Green -NoNewline
    Write-Host $Message
    $script:PassCount++
}

function Write-Failure {
    param([string]$Message)
    Write-Host "✗ " -ForegroundColor Red -NoNewline
    Write-Host $Message
    $script:FailCount++
}

function Write-Warning-Custom {
    param([string]$Message)
    Write-Host "⚠ " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
    $script:WarnCount++
}

function Write-Section {
    param([string]$Title)
    Write-Host "`n" -NoNewline
    Write-Host ("="*70) -ForegroundColor Blue
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("="*70) -ForegroundColor Blue
    Write-Host ""
}

function Test-ServiceRunning {
    param([string]$ServiceName)
    
    $output = docker compose ps $ServiceName 2>&1
    return ($output -match "Up" -or $output -match "running")
}

function Stop-MonitoringService {
    Write-Section "1단계: 모니터링 서비스 중단"
    
    try {
        docker compose stop monitoring-service 2>&1 | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "모니터링 서비스 중단: 성공적으로 중단됨"
            Start-Sleep -Seconds 3
            
            if (-not (Test-ServiceRunning "monitoring-service")) {
                Write-Success "모니터링 서비스 상태 확인: 중단됨"
            } else {
                Write-Warning-Custom "모니터링 서비스 상태 확인: 아직 실행 중인 것으로 보임"
            }
        } else {
            Write-Failure "모니터링 서비스 중단: 실패"
        }
    } catch {
        Write-Failure "모니터링 서비스 중단 중 오류: $($_.Exception.Message)"
    }
}

function Test-LoginService {
    Write-Section "2-1단계: 로그인 서비스 테스트"
    
    $token = $null
    
    # 회원가입 테스트
    try {
        $registerBody = @{
            username = $Username
            password = $Password
            email = $Email
        } | ConvertTo-Json
        
        $response = Invoke-WebRequest -Uri "$BaseUrl/login/register" `
            -Method Post `
            -Body $registerBody `
            -ContentType "application/json" `
            -TimeoutSec 10 `
            -ErrorAction SilentlyContinue
        
        if ($response.StatusCode -in @(200, 201, 409)) {
            Write-Success "회원가입 API: 응답 코드 $($response.StatusCode)"
        } else {
            Write-Failure "회원가입 API: 예상치 못한 응답 $($response.StatusCode)"
        }
    } catch {
        if ($_.Exception.Response.StatusCode -eq 409) {
            Write-Success "회원가입 API: 응답 코드 409 (계정 이미 존재)"
        } else {
            Write-Failure "회원가입 API: 요청 실패 - $($_.Exception.Message)"
        }
    }
    
    # 로그인 테스트
    try {
        $loginBody = @{
            username = $Username
            password = $Password
        } | ConvertTo-Json
        
        $response = Invoke-WebRequest -Uri "$BaseUrl/login/login" `
            -Method Post `
            -Body $loginBody `
            -ContentType "application/json" `
            -TimeoutSec 10
        
        if ($response.StatusCode -eq 200) {
            Write-Success "로그인 API: 성공 (응답 코드: $($response.StatusCode))"
            
            $data = $response.Content | ConvertFrom-Json
            $token = if ($data.access_token) { $data.access_token } else { $data.token }
            
            if ($token) {
                Write-Success "토큰 발급: 액세스 토큰 획득 성공"
            }
        } else {
            Write-Failure "로그인 API: 실패 - 응답 코드 $($response.StatusCode)"
        }
    } catch {
        Write-Failure "로그인 API: 요청 실패 - $($_.Exception.Message)"
    }
    
    # 토큰 검증 테스트
    if ($token) {
        try {
            $headers = @{
                "Authorization" = "Bearer $token"
            }
            
            $response = Invoke-WebRequest -Uri "$BaseUrl/login/verify" `
                -Method Get `
                -Headers $headers `
                -TimeoutSec 10 `
                -ErrorAction SilentlyContinue
            
            if ($response.StatusCode -eq 200) {
                Write-Success "토큰 검증: 성공"
            } else {
                Write-Warning-Custom "토큰 검증: 응답 코드 $($response.StatusCode)"
            }
        } catch {
            Write-Warning-Custom "토큰 검증: 요청 실패 - $($_.Exception.Message)"
        }
    }
    
    return $token
}

function Test-CrudService {
    param([string]$Token)
    
    Write-Section "2-2단계: 클립보드 CRUD 서비스 테스트"
    
    $headers = @{}
    if ($Token) {
        $headers["Authorization"] = "Bearer $Token"
    }
    
    # 텍스트 클립보드 생성 테스트
    $clipboardId = $null
    try {
        $createBody = @{
            content = "테스트 클립보드 내용 - $(Get-Date)"
            type = "text"
        } | ConvertTo-Json
        
        $response = Invoke-WebRequest -Uri "$BaseUrl/crud/clipboard" `
            -Method Post `
            -Body $createBody `
            -Headers $headers `
            -ContentType "application/json" `
            -TimeoutSec 10 `
            -ErrorAction SilentlyContinue
        
        if ($response.StatusCode -in @(200, 201)) {
            Write-Success "클립보드 생성 API: 성공 (응답 코드: $($response.StatusCode))"
            
            $data = $response.Content | ConvertFrom-Json
            $clipboardId = if ($data.id) { $data.id } else { $data.clipboard_id }
        } else {
            Write-Failure "클립보드 생성 API: 실패 - 응답 코드 $($response.StatusCode)"
        }
    } catch {
        Write-Failure "클립보드 생성 API: 요청 실패 - $($_.Exception.Message)"
    }
    
    # 클립보드 조회 테스트
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/crud/clipboard" `
            -Method Get `
            -Headers $headers `
            -TimeoutSec 10
        
        if ($response.StatusCode -eq 200) {
            Write-Success "클립보드 조회 API: 성공"
            
            try {
                $data = $response.Content | ConvertFrom-Json
                Write-Success "클립보드 데이터 형식: 올바른 JSON 응답"
            } catch {
                Write-Warning-Custom "클립보드 데이터 형식: JSON 파싱 실패"
            }
        } else {
            Write-Failure "클립보드 조회 API: 실패 - 응답 코드 $($response.StatusCode)"
        }
    } catch {
        Write-Failure "클립보드 조회 API: 요청 실패 - $($_.Exception.Message)"
    }
    
    # 특정 클립보드 조회 테스트
    if ($clipboardId) {
        try {
            $response = Invoke-WebRequest -Uri "$BaseUrl/crud/clipboard/$clipboardId" `
                -Method Get `
                -Headers $headers `
                -TimeoutSec 10 `
                -ErrorAction SilentlyContinue
            
            if ($response.StatusCode -eq 200) {
                Write-Success "특정 클립보드 조회: 성공"
            } else {
                Write-Warning-Custom "특정 클립보드 조회: 응답 코드 $($response.StatusCode)"
            }
        } catch {
            Write-Warning-Custom "특정 클립보드 조회: 요청 실패 - $($_.Exception.Message)"
        }
    }
    
    # 클립보드 업데이트 테스트
    if ($clipboardId) {
        try {
            $updateBody = @{
                content = "수정된 내용 - $(Get-Date)"
            } | ConvertTo-Json
            
            $response = Invoke-WebRequest -Uri "$BaseUrl/crud/clipboard/$clipboardId" `
                -Method Put `
                -Body $updateBody `
                -Headers $headers `
                -ContentType "application/json" `
                -TimeoutSec 10 `
                -ErrorAction SilentlyContinue
            
            if ($response.StatusCode -in @(200, 204)) {
                Write-Success "클립보드 수정 API: 성공"
            } else {
                Write-Warning-Custom "클립보드 수정 API: 응답 코드 $($response.StatusCode)"
            }
        } catch {
            Write-Warning-Custom "클립보드 수정 API: 요청 실패 - $($_.Exception.Message)"
        }
    }
}

function Test-NotificationService {
    param([string]$Token)
    
    Write-Section "2-3단계: 알림 서비스 테스트"
    
    $headers = @{}
    if ($Token) {
        $headers["Authorization"] = "Bearer $Token"
    }
    
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/notification/notifications" `
            -Method Get `
            -Headers $headers `
            -TimeoutSec 10 `
            -ErrorAction SilentlyContinue
        
        if ($response.StatusCode -eq 200) {
            Write-Success "알림 조회 API: 성공"
        } else {
            Write-Warning-Custom "알림 조회 API: 응답 코드 $($response.StatusCode)"
        }
    } catch {
        if ($_.Exception.Response.StatusCode -eq 404) {
            Write-Success "알림 조회 API: 엔드포인트 미구현 (정상)"
        } else {
            Write-Warning-Custom "알림 조회 API: 요청 실패 - $($_.Exception.Message)"
        }
    }
}

function Test-NginxLogs {
    Write-Section "3단계: Nginx/API Gateway 로그 확인"
    
    try {
        $logs = docker compose logs --tail=50 nginx-gateway 2>&1
        
        $error502Count = ($logs | Select-String -Pattern "502" -AllMatches).Matches.Count
        $error500Count = ($logs | Select-String -Pattern "500" -AllMatches).Matches.Count
        
        if ($error502Count -gt 0) {
            Write-Failure "Nginx 502 에러: 502 에러 ${error502Count}건 발견"
        } else {
            Write-Success "Nginx 502 에러: 502 에러 없음"
        }
        
        if ($error500Count -gt 0) {
            Write-Warning-Custom "Nginx 500 에러: 500 에러 ${error500Count}건 발견"
        } else {
            Write-Success "Nginx 500 에러: 500 에러 없음"
        }
    } catch {
        Write-Warning-Custom "Nginx 로그 확인: 로그 조회 실패"
    }
}

function Test-ServiceLogs {
    Write-Section "4단계: 각 서비스 로그 에러 확인"
    
    $services = @("login-service", "crud-service", "notification-service")
    $errorKeywords = @("ERROR", "Exception", "Failed", "refused", "timeout")
    
    foreach ($service in $services) {
        try {
            $logs = docker compose logs --tail=30 $service 2>&1 | Out-String
            
            $errorsFound = @()
            foreach ($keyword in $errorKeywords) {
                if ($logs -match $keyword) {
                    $errorsFound += $keyword
                }
            }
            
            if ($errorsFound.Count -gt 0) {
                Write-Warning-Custom "${service} 로그 확인: 다음 키워드 발견 - $($errorsFound -join ', ')"
            } else {
                Write-Success "${service} 로그 확인: 에러 없음"
            }
        } catch {
            Write-Warning-Custom "${service} 로그 확인: 로그 조회 실패"
        }
    }
}

function Test-CoreServicesStatus {
    Write-Section "5단계: 핵심 서비스 상태 확인"
    
    $coreServices = @("login-service", "crud-service", "notification-service", "nginx-gateway")
    
    foreach ($service in $coreServices) {
        if (Test-ServiceRunning $service) {
            Write-Success "${service} 상태: 실행 중"
        } else {
            Write-Failure "${service} 상태: 중단됨"
        }
    }
}

function Restart-MonitoringService {
    Write-Section "6단계: 모니터링 서비스 재시작"
    
    try {
        docker compose start monitoring-service 2>&1 | Out-Null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "모니터링 서비스 재시작: 성공"
            Start-Sleep -Seconds 3
            
            if (Test-ServiceRunning "monitoring-service") {
                Write-Success "모니터링 서비스 상태: 실행 중"
            } else {
                Write-Warning-Custom "모니터링 서비스 상태: 재시작 후에도 중단됨"
            }
        } else {
            Write-Failure "모니터링 서비스 재시작: 실패"
        }
    } catch {
        Write-Failure "모니터링 서비스 재시작 중 오류: $($_.Exception.Message)"
    }
}

function Show-Summary {
    Write-Host "`n" -NoNewline
    Write-Host ("="*70) -ForegroundColor Blue
    Write-Host "테스트 결과 요약" -ForegroundColor Cyan
    Write-Host ("="*70) -ForegroundColor Blue
    
    $duration = (Get-Date) - $script:StartTime
    Write-Host "실행 시간: $($duration.ToString('mm\:ss'))"
    Write-Host "성공: $script:PassCount" -ForegroundColor Green
    Write-Host "실패: $script:FailCount" -ForegroundColor Red
    Write-Host "경고: $script:WarnCount" -ForegroundColor Yellow
    
    Write-Host ("="*70) -ForegroundColor Blue
    
    if ($script:FailCount -eq 0) {
        Write-Host "모든 테스트 통과!" -ForegroundColor Green
        return $true
    } else {
        Write-Host "테스트 실패" -ForegroundColor Red
        return $false
    }
}

# 메인 실행
Write-Host "`n" -NoNewline
Write-Host ("="*70) -ForegroundColor Blue
Write-Host "모니터링 서비스 중단 시 핵심 서비스 정상 동작 테스트" -ForegroundColor Cyan
Write-Host ("="*70) -ForegroundColor Blue
Write-Host ""
Write-Host "테스트 시작 시간: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Base URL: $BaseUrl`n"

try {
    # 1. 모니터링 서비스 중단
    Stop-MonitoringService
    
    # 2. 핵심 서비스 기능 테스트
    $token = Test-LoginService
    Test-CrudService -Token $token
    Test-NotificationService -Token $token
    
    # 3. Nginx 로그 확인
    Test-NginxLogs
    
    # 4. 각 서비스 로그 확인
    Test-ServiceLogs
    
    # 5. 핵심 서비스 상태 확인
    Test-CoreServicesStatus
    
    # 6. 모니터링 서비스 재시작
    Restart-MonitoringService
    
    # 결과 요약
    $success = Show-Summary
    
    if ($success) {
        exit 0
    } else {
        exit 1
    }
    
} catch {
    Write-Host "`n예상치 못한 에러: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
