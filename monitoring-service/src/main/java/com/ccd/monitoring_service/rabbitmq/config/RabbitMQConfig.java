package com.ccd.monitoring_service.rabbitmq.config;


import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitMQConfig {
    // 큐와 익스체인지 이름은 상수로 관리하는 게 편합니다.
    public static final String QUEUE_NAME = "monitoring.queue";
    public static final String EXCHANGE_NAME = "monitoring.exchange";
    public static final String ROUTING_KEY = "#";


    @Value("${spring.rabbitmq.host}")
    private String HOSTNAME;
    @Value("${spring.rabbitmq.port}")
    private Integer PORT;
    @Value("${spring.rabbitmq.username}")
    private String USERNAME;
    @Value("${spring.rabbitmq.password}")
    private String PASSWORD;

/**
     * 1. Queue 생성
     * durable = true: RabbitMQ가 재시작되어도 큐가 사라지지 않음
     */
    @Bean
    public Queue queue() {
        return new Queue(QUEUE_NAME, true);
    }

    @Bean
    public TopicExchange exchange() {
        return new TopicExchange(EXCHANGE_NAME);
    }

    /**
     * 3. Binding 생성
     * Queue와 Exchange를 Routing Key로 연결
     */
    @Bean
    public Binding binding(Queue queue, TopicExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(ROUTING_KEY);
    }

    /**
     * 4. MessageConverter 설정 (필수!)
     * Java 객체를 JSON으로 직렬화/역직렬화 해줍니다.
     * 이거 없으면 메시지가 알 수 없는 byte 코드로 보입니다.
     */
    @Bean
    public MessageConverter jsonMessageConverter() {
        return new JacksonJsonMessageConverter();
    }

    /**
     * 5. RabbitTemplate 설정
     * 위에서 만든 JSON Converter를 템플릿에 적용합니다.
     */
    @Bean
    public RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate rabbitTemplate = new RabbitTemplate(connectionFactory);
        rabbitTemplate.setMessageConverter(jsonMessageConverter());
        return rabbitTemplate;
    }
}
