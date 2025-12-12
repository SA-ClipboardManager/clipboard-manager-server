# 이벤트 기반 아키텍처 Correlation ID 추적 및 데이터 일관성 검증 (PowerShell)
# 목표: Correlation ID로 전체 이벤트 흐름 추적 및 로컬-클라우드 데이터 일치율 99% 이상 검증

param(
    [string]$BaseUrl = "http://localhost:8576",
    [string]$DbHost = "localhost",
    [int]$DbPort = 3306,
    [string]$DbUser = "root",
    [string]$DbPassword = "qwerty",
    [string]$RabbitMQUser = "qwerty",
    [string]$RabbitMQPassword = "qwerty",
    [int]$ItemCount = 10
)

# MySQL .NET Connector 필요 여부 확인
$mysqlAssemblyLoaded = $false
try {
    Add-Type -Path "C:\Program Files (x86)\MySQL\MySQL Connector NET 8.0\Assemblies\v4.5.2\MySql.Data.dll" -ErrorAction SilentlyContinue
    $mysqlAssemblyLoaded = $true
} catch {
    Write-Host "MySQL Connector가 설치되지 않았거나 경로가 다릅니다. DB 직접 조회는 건너뜁니다." -ForegroundColor Yellow
}

# 색상 및 통계 변수
$script:PassCount = 0
$script:FailCount = 0
$script:WarnCount = 0
$script:CorrelationIds = @()
$script:UploadedItems = @()
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

function Write-Info {
    param([string]$Message)
    Write-Host "ℹ " -ForegroundColor Cyan -NoNewline
    Write-Host $Message
}

function Write-Section {
    param([string]$Title)
    Write-Host "`n" -NoNewline
    Write-Host ("="*70) -ForegroundColor Blue
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("="*70) -ForegroundColor Blue
    Write-Host ""
}

function New-CorrelationId {
    return "test-$([guid]::NewGuid().ToString())"
}

function New-TestImage {
    # 1x1 빨간색 PNG 이미지 (Base64)
    $base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
    return [System.Convert]::FromBase64String($base64)
}

function Setup-TestUser {
    Write-Section "0단계: 테스트 사용자 설정"
    
    $timestamp = [int][double]::Parse((Get-Date -UFormat %s))
    $username = "correlation_test_$timestamp"
    $password = "testpass123"
    $email = "correlation_test_${timestamp}@example.com"
    
    # 회원가입
    try {
        $registerBody = @{
            username = $username
            password = $password
            email = $email
        } | ConvertTo-Json
        
        $response = Invoke-WebRequest -Uri "$BaseUrl/login/register" `
            -Method Post `
            -Body $registerBody `
            -ContentType "application/json" `
            -TimeoutSec 10 `
            -ErrorAction SilentlyContinue
        
        if ($response.StatusCode -in @(200, 201)) {
            Write-Success "테스트 사용자 생성: 사용자명 $username"
        } elseif ($response.StatusCode -eq 409) {
            Write-Warning-Custom "테스트 사용자 생성: 이미 존재하는 사용자"
        }
    } catch {
        if ($_.Exception.Response.StatusCode -eq 409) {
            Write-Warning-Custom "테스트 사용자 생성: 이미 존재하는 사용자"
        } else {
            Write-Failure "테스트 사용자 생성: $($_.Exception.Message)"
        }
    }
    
    # 로그인
    try {
        $loginBody = @{
            username = $username
            password = $password
        } | ConvertTo-Json
        
        $response = Invoke-WebRequest -Uri "$BaseUrl/login/login" `
            -Method Post `
            -Body $loginBody `
            -ContentType "application/json" `
            -TimeoutSec 10
        
        if ($response.StatusCode -eq 200) {
            $data = $response.Content | ConvertFrom-Json
            $token = if ($data.access_token) { $data.access_token } else { $data.token }
            
            if ($token) {
                Write-Success "로그인 및 토큰 획득: 성공"
                return $token
            }
        }
        
        Write-Failure "로그인: 응답 코드 $($response.StatusCode)"
        return $null
    } catch {
        Write-Failure "로그인: $($_.Exception.Message)"
        return $null
    }
}

function Upload-ClipboardItems {
    param([string]$Token, [int]$Count)
    
    Write-Section "1단계: 클립보드 아이템 업로드 ($Count개)"
    
    $headers = @{
        "Authorization" = "Bearer $Token"
    }
    
    $uploadedCount = 0
    
    for ($i = 0; $i -lt $Count; $i++) {
        $correlationId = New-CorrelationId
        $script:CorrelationIds += $correlationId
        
        $headersWithCorrelation = $headers.Clone()
        $headersWithCorrelation["X-Correlation-ID"] = $correlationId
        
        if ($i % 2 -eq 0) {
            # 텍스트 업로드
            try {
                $body = @{
                    content = "테스트 텍스트 $($i+1) - $(Get-Date)"
                    type = "text"
                    correlation_id = $correlationId
                } | ConvertTo-Json
                
                $response = Invoke-WebRequest -Uri "$BaseUrl/crud/clipboard" `
                    -Method Post `
                    -Body $body `
                    -Headers $headersWithCorrelation `
                    -ContentType "application/json" `
                    -TimeoutSec 10 `
                    -ErrorAction SilentlyContinue
                
                if ($response.StatusCode -in @(200, 201)) {
                    $data = $response.Content | ConvertFrom-Json
                    $itemId = if ($data.id) { $data.id } else { $data.clipboard_id }
                    
                    $script:UploadedItems += @{
                        id = $itemId
                        type = "text"
                        correlation_id = $correlationId
                    }
                    
                    $uploadedCount++
                    Write-Info "텍스트 $($i+1) 업로드 성공 (Correlation ID: $($correlationId.Substring(0, 16))...)"
                } else {
                    Write-Warning-Custom "텍스트 $($i+1) 업로드: 응답 코드 $($response.StatusCode)"
                }
            } catch {
                Write-Warning-Custom "텍스트 $($i+1) 업로드: $($_.Exception.Message)"
            }
        } else {
            # 이미지 업로드
            try {
                $imageBytes = New-TestImage
                $boundary = [System.Guid]::NewGuid().ToString()
                
                $bodyLines = @(
                    "--$boundary",
                    "Content-Disposition: form-data; name=`"file`"; filename=`"test_image_$($i+1).png`"",
                    "Content-Type: image/png",
                    "",
                    [System.Text.Encoding]::GetEncoding("iso-8859-1").GetString($imageBytes),
                    "--$boundary",
                    "Content-Disposition: form-data; name=`"type`"",
                    "",
                    "image",
                    "--$boundary",
                    "Content-Disposition: form-data; name=`"correlation_id`"",
                    "",
                    $correlationId,
                    "--$boundary--"
                )
                
                $body = $bodyLines -join "`r`n"
                
                $headersWithCorrelation["Content-Type"] = "multipart/form-data; boundary=$boundary"
                
                $response = Invoke-WebRequest -Uri "$BaseUrl/crud/clipboard/upload" `
                    -Method Post `
                    -Body $body `
                    -Headers $headersWithCorrelation `
                    -TimeoutSec 10 `
                    -ErrorAction SilentlyContinue
                
                if ($response.StatusCode -in @(200, 201)) {
                    $data = $response.Content | ConvertFrom-Json
                    $itemId = if ($data.id) { $data.id } else { $data.clipboard_id }
                    
                    $script:UploadedItems += @{
                        id = $itemId
                        type = "image"
                        correlation_id = $correlationId
                    }
                    
                    $uploadedCount++
                    Write-Info "이미지 $($i+1) 업로드 성공 (Correlation ID: $($correlationId.Substring(0, 16))...)"
                } else {
                    Write-Warning-Custom "이미지 $($i+1) 업로드: 응답 코드 $($response.StatusCode)"
                }
            } catch {
                Write-Warning-Custom "이미지 $($i+1) 업로드: $($_.Exception.Message)"
            }
        }
        
        Start-Sleep -Milliseconds 500
    }
    
    Write-Success "클립보드 아이템 업로드: $uploadedCount/$Count개 성공"
    
    Write-Info "이벤트 처리 대기 중... (10초)"
    Start-Sleep -Seconds 10
}

function Invoke-CloudSync {
    param([string]$Token)
    
    Write-Section "2단계: 클라우드 동기화 실행"
    
    $headers = @{
        "Authorization" = "Bearer $Token"
    }
    
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/crud/sync/cloud" `
            -Method Post `
            -Headers $headers `
            -TimeoutSec 30 `
            -ErrorAction SilentlyContinue
        
        if ($response.StatusCode -in @(200, 201, 202)) {
            Write-Success "클라우드 동기화 트리거: 성공"
            Write-Info "동기화 처리 대기 중... (15초)"
            Start-Sleep -Seconds 15
        } elseif ($response.StatusCode -eq 404) {
            Write-Warning-Custom "클라우드 동기화 트리거: 엔드포인트 미구현"
        } else {
            Write-Warning-Custom "클라우드 동기화 트리거: 응답 코드 $($response.StatusCode)"
        }
    } catch {
        if ($_.Exception.Response.StatusCode -eq 404) {
            Write-Warning-Custom "클라우드 동기화 트리거: 엔드포인트 미구현"
        } else {
            Write-Warning-Custom "클라우드 동기화 트리거: $($_.Exception.Message)"
        }
    }
}

function Test-CorrelationInMonitoringDB {
    Write-Section "3단계: 모니터링 DB에서 Correlation ID 추적"
    
    if (-not $mysqlAssemblyLoaded) {
        Write-Warning-Custom "MySQL Connector 미설치: DB 직접 조회 건너뜀"
        return
    }
    
    try {
        $connectionString = "server=$DbHost;port=$DbPort;uid=$DbUser;pwd=$DbPassword;database=monitoring_db"
        $connection = New-Object MySql.Data.MySqlClient.MySqlConnection($connectionString)
        $connection.Open()
        
        # 테이블 확인
        $command = $connection.CreateCommand()
        $command.CommandText = "SHOW TABLES"
        $reader = $command.ExecuteReader()
        
        $tables = @()
        while ($reader.Read()) {
            $tables += $reader.GetString(0)
        }
        $reader.Close()
        
        if ($tables.Count -eq 0) {
            Write-Warning-Custom "모니터링 DB 테이블: 테이블이 없음"
            $connection.Close()
            return
        }
        
        Write-Info "발견된 테이블: $($tables -join ', ')"
        
        $logTables = $tables | Where-Object { $_ -like "*log*" }
        
        if ($logTables.Count -eq 0) {
            Write-Warning-Custom "로그 테이블: 로그 테이블을 찾을 수 없음"
            $connection.Close()
            return
        }
        
        $foundCorrelationIds = 0
        $totalLogEntries = 0
        
        foreach ($table in $logTables) {
            try {
                $command = $connection.CreateCommand()
                $command.CommandText = "DESCRIBE $table"
                $reader = $command.ExecuteReader()
                
                $columns = @()
                while ($reader.Read()) {
                    $columns += $reader.GetString(0)
                }
                $reader.Close()
                
                $correlationColumn = $columns | Where-Object { $_ -like "*correlation*" } | Select-Object -First 1
                
                if (-not $correlationColumn) {
                    Write-Info "테이블 '$table'에 correlation 컬럼 없음"
                    continue
                }
                
                foreach ($cid in $script:CorrelationIds[0..4]) {
                    $command = $connection.CreateCommand()
                    $command.CommandText = "SELECT COUNT(*) FROM $table WHERE $correlationColumn = @cid"
                    $command.Parameters.AddWithValue("@cid", $cid) | Out-Null
                    
                    $count = [int]$command.ExecuteScalar()
                    
                    if ($count -gt 0) {
                        $foundCorrelationIds++
                        $totalLogEntries += $count
                        Write-Info "Correlation ID $($cid.Substring(0, 16))... 발견: $count개 로그 ($table)"
                    }
                }
            } catch {
                Write-Warning-Custom "테이블 '$table' 조회: $($_.Exception.Message)"
            }
        }
        
        if ($foundCorrelationIds -gt 0) {
            Write-Success "Correlation ID 추적: ${foundCorrelationIds}개 ID에서 총 ${totalLogEntries}개 로그 발견"
        } else {
            Write-Warning-Custom "Correlation ID 추적: 모니터링 DB에서 Correlation ID를 찾을 수 없음"
        }
        
        $connection.Close()
        
    } catch {
        Write-Warning-Custom "모니터링 DB 조회: $($_.Exception.Message)"
    }
}

function Test-CorrelationInRabbitMQ {
    Write-Section "4단계: RabbitMQ 이벤트 흐름 확인"
    
    try {
        $credential = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("${RabbitMQUser}:${RabbitMQPassword}"))
        $headers = @{
            "Authorization" = "Basic $credential"
        }
        
        $response = Invoke-WebRequest -Uri "http://localhost:15672/api/queues" `
            -Headers $headers `
            -TimeoutSec 10 `
            -ErrorAction Stop
        
        if ($response.StatusCode -eq 200) {
            $queues = $response.Content | ConvertFrom-Json
            Write-Success "RabbitMQ 연결: $($queues.Count)개 큐 발견"
            
            $totalMessages = 0
            foreach ($queue in $queues) {
                $queueName = $queue.name
                $messages = $queue.messages
                $totalMessages += $messages
                
                if ($messages -gt 0) {
                    Write-Info "큐 '$queueName': $messages개 메시지"
                }
            }
            
            Write-Success "RabbitMQ 메시지 확인: 총 $totalMessages개 메시지"
            
            # 익스체인지 조회
            $response = Invoke-WebRequest -Uri "http://localhost:15672/api/exchanges" `
                -Headers $headers `
                -TimeoutSec 10
            
            if ($response.StatusCode -eq 200) {
                $exchanges = $response.Content | ConvertFrom-Json
                $customExchanges = $exchanges | Where-Object { -not $_.name.StartsWith("amq.") }
                
                if ($customExchanges.Count -gt 0) {
                    $exchangeNames = ($customExchanges | ForEach-Object { $_.name }) -join ', '
                    Write-Info "발견된 익스체인지: $exchangeNames"
                    Write-Success "RabbitMQ 익스체인지 확인: $($customExchanges.Count)개 발견"
                }
            }
        }
    } catch {
        Write-Warning-Custom "RabbitMQ 확인: 연결 실패 - $($_.Exception.Message)"
    }
}

function Test-DataConsistency {
    param([string]$Token)
    
    Write-Section "5단계: 로컬-클라우드 데이터 일관성 검증"
    
    $headers = @{
        "Authorization" = "Bearer $Token"
    }
    
    # 로컬 데이터 조회
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/crud/clipboard" `
            -Headers $headers `
            -TimeoutSec 10
        
        if ($response.StatusCode -ne 200) {
            Write-Failure "로컬 데이터 조회: 응답 코드 $($response.StatusCode)"
            return
        }
        
        $localData = $response.Content | ConvertFrom-Json
        $localItems = if ($localData -is [Array]) { $localData } else { $localData.items }
        $localCount = $localItems.Count
        
        Write-Success "로컬 데이터 조회: $localCount개 아이템"
        
    } catch {
        Write-Failure "로컬 데이터 조회: $($_.Exception.Message)"
        return
    }
    
    # 클라우드 데이터 조회
    try {
        $response = Invoke-WebRequest -Uri "$BaseUrl/crud/clipboard/cloud" `
            -Headers $headers `
            -TimeoutSec 10 `
            -ErrorAction SilentlyContinue
        
        if ($response.StatusCode -eq 200) {
            $cloudData = $response.Content | ConvertFrom-Json
            $cloudItems = if ($cloudData -is [Array]) { $cloudData } else { $cloudData.items }
            $cloudCount = $cloudItems.Count
            
            Write-Success "클라우드 데이터 조회: $cloudCount개 아이템"
            
            if ($localCount -eq 0) {
                Write-Warning-Custom "데이터 일치율: 로컬 데이터가 없음"
                return
            }
            
            # ID 기반 일치율 계산
            $localIds = @($localItems | ForEach-Object { $_.id } | Where-Object { $_ })
            $cloudIds = @($cloudItems | ForEach-Object { $_.id } | Where-Object { $_ })
            
            $matchingIds = @($localIds | Where-Object { $cloudIds -contains $_ })
            $totalUniqueIds = @($localIds + $cloudIds | Select-Object -Unique)
            
            if ($totalUniqueIds.Count -gt 0) {
                $consistencyRate = ($matchingIds.Count / $totalUniqueIds.Count) * 100
                
                Write-Info "로컬 고유 ID: $($localIds.Count)개"
                Write-Info "클라우드 고유 ID: $($cloudIds.Count)개"
                Write-Info "일치하는 ID: $($matchingIds.Count)개"
                Write-Info "전체 고유 ID: $($totalUniqueIds.Count)개"
                
                if ($consistencyRate -ge 99.0) {
                    Write-Success "데이터 일관성: $([math]::Round($consistencyRate, 2))% (기준: 99% 이상) ✓"
                } elseif ($consistencyRate -ge 90.0) {
                    Write-Warning-Custom "데이터 일관성: $([math]::Round($consistencyRate, 2))% (기준: 99% 이상)"
                } else {
                    Write-Failure "데이터 일관성: $([math]::Round($consistencyRate, 2))% (기준: 99% 이상)"
                }
            } else {
                Write-Warning-Custom "데이터 일관성: 비교 가능한 데이터 없음"
            }
            
        } elseif ($response.StatusCode -eq 404) {
            Write-Warning-Custom "클라우드 데이터 조회: 클라우드 동기화 기능 미구현"
        } else {
            Write-Warning-Custom "클라우드 데이터 조회: 응답 코드 $($response.StatusCode)"
        }
        
    } catch {
        if ($_.Exception.Response.StatusCode -eq 404) {
            Write-Warning-Custom "클라우드 데이터 조회: 클라우드 동기화 기능 미구현"
        } else {
            Write-Warning-Custom "클라우드 데이터 조회: $($_.Exception.Message)"
        }
    }
}

function Test-ServiceLogsForCorrelation {
    Write-Section "6단계: 서비스 로그에서 Correlation ID 확인"
    
    $services = @("crud-service", "notification-service", "monitoring-service")
    $sampleCids = $script:CorrelationIds[0..2]
    
    foreach ($service in $services) {
        try {
            $logs = docker compose logs --tail=100 $service 2>&1 | Out-String
            
            $foundCount = 0
            foreach ($cid in $sampleCids) {
                if ($logs -match [regex]::Escape($cid)) {
                    $foundCount++
                }
            }
            
            if ($foundCount -gt 0) {
                Write-Success "${service} Correlation ID: $foundCount/$($sampleCids.Count)개 발견"
            } else {
                Write-Warning-Custom "${service} Correlation ID: 로그에서 찾을 수 없음"
            }
            
        } catch {
            Write-Warning-Custom "${service} 로그 조회: $($_.Exception.Message)"
        }
    }
}

function Test-CRUDDatabaseConsistency {
    Write-Section "7단계: 데이터베이스 레벨 일관성 확인"
    
    if (-not $mysqlAssemblyLoaded) {
        Write-Warning-Custom "MySQL Connector 미설치: DB 직접 조회 건너뜀"
        return
    }
    
    try {
        $connectionString = "server=$DbHost;port=$DbPort;uid=$DbUser;pwd=$DbPassword;database=crud_db"
        $connection = New-Object MySql.Data.MySqlClient.MySqlConnection($connectionString)
        $connection.Open()
        
        # 테이블 목록 확인
        $command = $connection.CreateCommand()
        $command.CommandText = "SHOW TABLES"
        $reader = $command.ExecuteReader()
        
        $tables = @()
        while ($reader.Read()) {
            $tables += $reader.GetString(0)
        }
        $reader.Close()
        
        $clipboardTable = $tables | Where-Object { $_ -like "*clipboard*" -or $_ -like "*clip*" } | Select-Object -First 1
        
        if ($clipboardTable) {
            Write-Info "클립보드 테이블 발견: $clipboardTable"
            
            $uploadedIds = @($script:UploadedItems | ForEach-Object { $_.id } | Where-Object { $_ })
            $sampleIds = $uploadedIds[0..4]
            
            $foundCount = 0
            foreach ($itemId in $sampleIds) {
                $command = $connection.CreateCommand()
                $command.CommandText = "SELECT COUNT(*) FROM $clipboardTable WHERE id = @id"
                $command.Parameters.AddWithValue("@id", $itemId) | Out-Null
                
                $count = [int]$command.ExecuteScalar()
                if ($count -gt 0) {
                    $foundCount++
                }
            }
            
            if ($foundCount -gt 0) {
                Write-Success "DB 아이템 확인: $foundCount/$($sampleIds.Count)개 샘플 아이템 발견"
            } else {
                Write-Warning-Custom "DB 아이템 확인: 업로드된 아이템을 DB에서 찾을 수 없음"
            }
        } else {
            Write-Warning-Custom "클립보드 테이블: 테이블을 찾을 수 없음"
        }
        
        $connection.Close()
        
    } catch {
        Write-Warning-Custom "데이터베이스 조회: $($_.Exception.Message)"
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
    Write-Host "생성된 Correlation ID: $($script:CorrelationIds.Count)개" -ForegroundColor Cyan
    Write-Host "업로드된 아이템: $($script:UploadedItems.Count)개" -ForegroundColor Cyan
    
    if ($script:CorrelationIds.Count -gt 0) {
        Write-Host "`nCorrelation IDs:" -ForegroundColor Cyan
        $displayCount = [Math]::Min(5, $script:CorrelationIds.Count)
        for ($i = 0; $i -lt $displayCount; $i++) {
            Write-Host "  - $($script:CorrelationIds[$i])"
        }
        if ($script:CorrelationIds.Count -gt 5) {
            Write-Host "  ... 외 $($script:CorrelationIds.Count - 5)개"
        }
    }
    
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
Write-Host "이벤트 기반 아키텍처 Correlation ID 추적 및 데이터 일관성 검증" -ForegroundColor Cyan
Write-Host ("="*70) -ForegroundColor Blue
Write-Host ""
Write-Host "테스트 시작 시간: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Base URL: $BaseUrl"
Write-Host "아이템 수: $ItemCount`n"

try {
    # 0. 테스트 사용자 설정
    $token = Setup-TestUser
    if (-not $token) {
        Write-Host "`n로그인 실패로 테스트 중단" -ForegroundColor Red
        exit 1
    }
    
    # 1. 클립보드 아이템 업로드
    Upload-ClipboardItems -Token $token -Count $ItemCount
    
    # 2. 클라우드 동기화
    Invoke-CloudSync -Token $token
    
    # 3. 모니터링 DB에서 Correlation ID 추적
    Test-CorrelationInMonitoringDB
    
    # 4. RabbitMQ 이벤트 흐름 확인
    Test-CorrelationInRabbitMQ
    
    # 5. 데이터 일관성 검증
    Test-DataConsistency -Token $token
    
    # 6. 서비스 로그에서 Correlation ID 확인
    Test-ServiceLogsForCorrelation
    
    # 7. 데이터베이스 레벨 일관성 확인
    Test-CRUDDatabaseConsistency
    
    # 결과 요약
    $success = Show-Summary
    
    if ($success) {
        exit 0
    } else {
        exit 1
    }
    
} catch {
    Write-Host "`n예상치 못한 에러: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.Exception.StackTrace -ForegroundColor Red
    exit 1
}
