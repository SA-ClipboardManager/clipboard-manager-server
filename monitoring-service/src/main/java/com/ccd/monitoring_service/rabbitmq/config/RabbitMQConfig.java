package com.ccd.monitoring_service.rabbitmq.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitMQConfig {

    public static final String MONITORING_MAIN_EXCHANGE = "main.exchange";
    public static final String MONITORING_RECOVERY_EXCHANGE ="recovery.exchange";
    // --- 1. Queue 이름 정의 ---
    public static final String QUEUE_MAIN = "monitoring.queue";          // fail로그 수집용 메인 큐
    public static final String QUEUE_RETRY = "monitoring.retry.queue"; // 재시도용 큐

    // --- 2. Routing Key 정의 (흐름순) ---
    // (1) 외부에서 로그가 들어올 때: "embedding.success", "crd.error" 등
    public static final String ROUTING_KEY_MAIN_PATTERN = "service.#";

    // (2) MessageConsumer -> FailureHandler로 보낼 때 ("monitoring.fail_occur")
    public static final String ROUTING_KEY_FAIL = "monitoring.fail_occur";

    // (4) 외부 서비스에서 재시도하고 결과를 모니터링 서비스로 보낼 때
    public static final String ROUTING_KEY_RETRY = "*.retry.#";
    /* 참고
     * 어떤 서비스로 재시도 요청 보낼 떄 routing key
     *  *.[serviceName].do.retry   ex)crud.do.retry
     * */

    // --- 3. Queue Bean 생성 ---
    @Bean
    public Queue mainQueue() {
        return new Queue(QUEUE_MAIN, true);
    }

    @Bean
    public Queue retryQueue() {
        // FailureHandler가 "롤백 해!"라고 던지면 받아줄 큐 (나중에 결제 서비스 등이 리스닝)
        return new Queue(QUEUE_RETRY, true);
    }

    // --- 4. Exchange Bean 생성 ---
    @Bean
    public TopicExchange mainExchange() {
        return new TopicExchange(MONITORING_MAIN_EXCHANGE);
    }

    @Bean
    public TopicExchange recoveryExchange() {
        return new TopicExchange(MONITORING_RECOVERY_EXCHANGE);
    }
    // --- 5. Binding (Exchange와 Queue 연결) ---

    // A. 메인 큐 연결: "service"로 시작하는 모든 메시지는 Main Queue로
    @Bean
    public Binding bindingMain(Queue mainQueue, TopicExchange mainExchange) {
        return BindingBuilder.bind(mainQueue).to(mainExchange).with(ROUTING_KEY_MAIN_PATTERN);
    }

    // B. 재시도 수행 큐 연결: ___service가 모니터링 서비스로 이벤트 보내면 Retry Queue로
    @Bean
    public Binding bindingRetry(Queue retryQueue, TopicExchange recoveryExchange) {
        return BindingBuilder.bind(retryQueue).to(recoveryExchange).with(ROUTING_KEY_RETRY);
    }

    // C. 새로운 실패 수신용
    @Bean
    public Binding bindingFail(Queue retryQueue, TopicExchange recoveryExchange) {
        return BindingBuilder.bind(retryQueue).to(recoveryExchange).with(ROUTING_KEY_FAIL);
    }

    // --- 6. Converter & Template ---
    @Bean
    public MessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    public RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate rabbitTemplate = new RabbitTemplate(connectionFactory);
        rabbitTemplate.setMessageConverter(jsonMessageConverter());
        return rabbitTemplate;
    }
}