-- EAI-Flow workflow subsystem
-- Faithful MySQL migration for warm-flow 8 core tables.
-- Source: warm-flow-master/sql/mysql/warm-flow-all.sql (+ flow_form from core entity).

CREATE TABLE IF NOT EXISTS `flow_definition`
(
    `id`              bigint       NOT NULL COMMENT '主键id',
    `flow_code`       varchar(40)  NOT NULL COMMENT '流程编码',
    `flow_name`       varchar(100) NOT NULL COMMENT '流程名称',
    `model_value`     varchar(40)  NOT NULL DEFAULT 'CLASSICS' COMMENT 'CLASSICS经典模型',
    `category`        varchar(100)          DEFAULT NULL COMMENT '流程类别',
    `version`         varchar(20)  NOT NULL COMMENT '流程版本',
    `is_publish`      tinyint(1)   NOT NULL DEFAULT 0 COMMENT '0未发布 1已发布 9已失效',
    `form_custom`     char(1)               DEFAULT 'N' COMMENT '审批表单是否自定义 Y/N',
    `form_path`       varchar(100)          DEFAULT NULL COMMENT '审批表单路径',
    `activity_status` tinyint(1)   NOT NULL DEFAULT 1 COMMENT '0挂起 1激活',
    `listener_type`   varchar(100)          DEFAULT NULL COMMENT '监听器类型',
    `listener_path`   varchar(400)          DEFAULT NULL COMMENT '监听器路径',
    `ext`             varchar(500)          DEFAULT NULL COMMENT '业务扩展',
    `create_time`     datetime              DEFAULT NULL,
    `create_by`       varchar(64)           DEFAULT '',
    `update_time`     datetime              DEFAULT NULL,
    `update_by`       varchar(64)           DEFAULT '',
    `del_flag`        char(1)               DEFAULT '0',
    `tenant_id`       varchar(40)           DEFAULT NULL,
    PRIMARY KEY (`id`) USING BTREE,
    KEY `idx_def_code` (`flow_code`),
    KEY `idx_def_publish` (`flow_code`, `is_publish`),
    KEY `idx_def_tenant` (`tenant_id`)
) ENGINE = InnoDB COMMENT ='流程定义表';

CREATE TABLE IF NOT EXISTS `flow_node`
(
    `id`              bigint       NOT NULL COMMENT '主键id',
    `node_type`       tinyint(1)   NOT NULL COMMENT '0开始 1中间 2结束 3互斥网关 4并行网关 5包容网关',
    `definition_id`   bigint       NOT NULL COMMENT '流程定义id',
    `node_code`       varchar(100) NOT NULL COMMENT '节点编码',
    `node_name`       varchar(100)          DEFAULT NULL COMMENT '节点名称',
    `permission_flag` varchar(1000)         DEFAULT NULL COMMENT '办理人标识，@@分隔',
    `node_ratio`      varchar(200)          DEFAULT NULL COMMENT '签署比例/策略',
    `coordinate`      varchar(200)          DEFAULT NULL COMMENT 'x,y|textX,textY',
    `any_node_skip`   varchar(100)          DEFAULT NULL COMMENT '任意跳转节点',
    `listener_type`   varchar(100)          DEFAULT NULL,
    `listener_path`   varchar(400)          DEFAULT NULL,
    `form_custom`     char(1)               DEFAULT 'N',
    `form_path`       varchar(100)          DEFAULT NULL,
    `version`         varchar(20)  NOT NULL,
    `create_time`     datetime              DEFAULT NULL,
    `create_by`       varchar(64)           DEFAULT '',
    `update_time`     datetime              DEFAULT NULL,
    `update_by`       varchar(64)           DEFAULT '',
    `ext`             text,
    `del_flag`        char(1)               DEFAULT '0',
    `tenant_id`       varchar(40)           DEFAULT NULL,
    PRIMARY KEY (`id`) USING BTREE,
    KEY `idx_node_def` (`definition_id`),
    KEY `idx_node_code` (`definition_id`, `node_code`),
    KEY `idx_node_tenant` (`tenant_id`)
) ENGINE = InnoDB COMMENT ='流程节点表';

CREATE TABLE IF NOT EXISTS `flow_skip`
(
    `id`             bigint       NOT NULL COMMENT '主键id',
    `definition_id`  bigint       NOT NULL,
    `now_node_code`  varchar(100) NOT NULL,
    `now_node_type`  tinyint(1)            DEFAULT NULL,
    `next_node_code` varchar(100) NOT NULL,
    `next_node_type` tinyint(1)            DEFAULT NULL,
    `skip_name`      varchar(100)          DEFAULT NULL,
    `skip_type`      varchar(40)           DEFAULT NULL COMMENT 'PASS/REJECT/NONE',
    `skip_condition` varchar(500)          DEFAULT NULL,
    `coordinate`     varchar(500)          DEFAULT NULL COMMENT 'x1,y1;x2,y2|textX,textY',
    `create_time`    datetime              DEFAULT NULL,
    `create_by`      varchar(64)           DEFAULT '',
    `update_time`    datetime              DEFAULT NULL,
    `update_by`      varchar(64)           DEFAULT '',
    `del_flag`       char(1)               DEFAULT '0',
    `tenant_id`      varchar(40)           DEFAULT NULL,
    PRIMARY KEY (`id`) USING BTREE,
    KEY `idx_skip_def` (`definition_id`),
    KEY `idx_skip_now` (`definition_id`, `now_node_code`),
    KEY `idx_skip_tenant` (`tenant_id`)
) ENGINE = InnoDB COMMENT ='节点跳转关联表';

CREATE TABLE IF NOT EXISTS `flow_instance`
(
    `id`              bigint      NOT NULL,
    `definition_id`   bigint      NOT NULL,
    `business_id`     varchar(100) NOT NULL,
    `node_type`       tinyint(1)  NOT NULL,
    `node_code`       varchar(40) NOT NULL,
    `node_name`       varchar(100)         DEFAULT NULL,
    `variable`        text,
    `flow_status`     varchar(20) NOT NULL,
    `activity_status` tinyint(1)  NOT NULL DEFAULT 1,
    `def_json`        longtext,
    `create_time`     datetime             DEFAULT NULL,
    `create_by`       varchar(64)          DEFAULT '',
    `update_time`     datetime             DEFAULT NULL,
    `update_by`       varchar(64)          DEFAULT '',
    `ext`             varchar(500)         DEFAULT NULL,
    `del_flag`        char(1)              DEFAULT '0',
    `tenant_id`       varchar(40)          DEFAULT NULL,
    PRIMARY KEY (`id`) USING BTREE,
    KEY `idx_ins_def` (`definition_id`),
    KEY `idx_ins_business` (`business_id`),
    KEY `idx_ins_status` (`flow_status`),
    KEY `idx_ins_tenant` (`tenant_id`)
) ENGINE = InnoDB COMMENT ='流程实例表';

CREATE TABLE IF NOT EXISTS `flow_task`
(
    `id`            bigint       NOT NULL,
    `definition_id` bigint       NOT NULL,
    `instance_id`   bigint       NOT NULL,
    `node_code`     varchar(100) NOT NULL,
    `node_name`     varchar(100)         DEFAULT NULL,
    `node_type`     tinyint(1)   NOT NULL,
    `flow_status`   varchar(20)  NOT NULL,
    `form_custom`   char(1)              DEFAULT 'N',
    `form_path`     varchar(100)         DEFAULT NULL,
    `create_time`   datetime             DEFAULT NULL,
    `create_by`     varchar(64)          DEFAULT '',
    `update_time`   datetime             DEFAULT NULL,
    `update_by`     varchar(64)          DEFAULT '',
    `del_flag`      char(1)              DEFAULT '0',
    `tenant_id`     varchar(40)          DEFAULT NULL,
    PRIMARY KEY (`id`) USING BTREE,
    KEY `idx_task_ins` (`instance_id`),
    KEY `idx_task_node` (`instance_id`, `node_code`),
    KEY `idx_task_tenant` (`tenant_id`)
) ENGINE = InnoDB COMMENT ='待办任务表';

CREATE TABLE IF NOT EXISTS `flow_his_task`
(
    `id`               bigint       NOT NULL,
    `definition_id`    bigint       NOT NULL,
    `instance_id`      bigint       NOT NULL,
    `task_id`          bigint       NOT NULL,
    `node_code`        varchar(100)          DEFAULT NULL,
    `node_name`        varchar(100)          DEFAULT NULL,
    `node_type`        tinyint(1)            DEFAULT NULL,
    `target_node_code` varchar(500)          DEFAULT NULL,
    `target_node_name` varchar(500)          DEFAULT NULL,
    `approver`         varchar(100)          DEFAULT NULL,
    `cooperate_type`   tinyint(1)   NOT NULL DEFAULT 0,
    `collaborator`     varchar(500)          DEFAULT NULL,
    `skip_type`        varchar(10)  NOT NULL,
    `flow_status`      varchar(20)  NOT NULL,
    `form_custom`      char(1)               DEFAULT 'N',
    `form_path`        varchar(100)          DEFAULT NULL,
    `message`          varchar(500)          DEFAULT NULL,
    `variable`         text,
    `ext`              text,
    `create_time`      datetime              DEFAULT NULL,
    `update_time`      datetime              DEFAULT NULL,
    `del_flag`         char(1)               DEFAULT '0',
    `tenant_id`        varchar(40)           DEFAULT NULL,
    PRIMARY KEY (`id`) USING BTREE,
    KEY `idx_his_ins` (`instance_id`),
    KEY `idx_his_task` (`task_id`),
    KEY `idx_his_approver` (`approver`),
    KEY `idx_his_tenant` (`tenant_id`)
) ENGINE = InnoDB COMMENT ='历史任务记录表';

CREATE TABLE IF NOT EXISTS `flow_user`
(
    `id`           bigint      NOT NULL,
    `type`         char(1)     NOT NULL COMMENT '1审批人 2转办人 3委托人',
    `processed_by` varchar(100) DEFAULT NULL,
    `associated`   bigint      NOT NULL COMMENT 'flow_task.id',
    `create_time`  datetime    DEFAULT NULL,
    `create_by`    varchar(80) DEFAULT NULL,
    `update_time`  datetime    DEFAULT NULL,
    `update_by`    varchar(64) DEFAULT '',
    `del_flag`     char(1)     DEFAULT '0',
    `tenant_id`    varchar(40) DEFAULT NULL,
    PRIMARY KEY (`id`) USING BTREE,
    KEY `user_processed_type` (`processed_by`, `type`),
    KEY `user_associated` (`associated`)
) ENGINE = InnoDB COMMENT ='流程用户表';

CREATE TABLE IF NOT EXISTS `flow_form`
(
    `id`            bigint       NOT NULL,
    `form_code`     varchar(100) NOT NULL,
    `form_name`     varchar(200) NOT NULL,
    `version`       varchar(20)  NOT NULL,
    `is_publish`    tinyint(1)   NOT NULL DEFAULT 0,
    `form_type`     tinyint(1)   NOT NULL DEFAULT 0 COMMENT '0内置 1外挂',
    `form_content`  longtext,
    `form_path`     varchar(200)          DEFAULT NULL,
    `ext`           varchar(500)          DEFAULT NULL,
    `create_time`   datetime              DEFAULT NULL,
    `create_by`     varchar(64)           DEFAULT '',
    `update_time`   datetime              DEFAULT NULL,
    `update_by`     varchar(64)           DEFAULT '',
    `del_flag`      char(1)               DEFAULT '0',
    `tenant_id`     varchar(40)           DEFAULT NULL,
    PRIMARY KEY (`id`) USING BTREE,
    KEY `idx_form_code` (`form_code`),
    KEY `idx_form_publish` (`form_code`, `is_publish`)
) ENGINE = InnoDB COMMENT ='流程表单表';
