# 1) Build Stage: Gradle로 Spring Boot JAR 빌드
FROM gradle:8.5-jdk21 AS builder
WORKDIR /app

# 프로젝트 전체 복사
COPY . .

# bootJar 생성
RUN gradle bootJar --no-daemon

# 2) Runtime Stage: Java 21 JRE 이미지
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
# builder에서 생성된 JAR 복사
COPY --from=builder /app/build/libs/*.jar app.jar

# JVM 최적화 옵션 (Worker 서비스에 적합)
ENV JAVA_OPTS="-XX:+UseG1GC -Duser.timezone=Asia/Seoul"

# Spring Boot 실행
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
