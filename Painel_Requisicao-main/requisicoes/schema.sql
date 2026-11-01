-- =============================================================================
-- Painel de Requisições · Esquema MySQL 8 / MariaDB 10.4+ (execução local)
-- Uso:  mysql -u root -p < schema.sql
-- Idempotente: pode ser executado novamente sem apagar dados.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS `painel_requisicoes`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `painel_requisicoes`;

-- -----------------------------------------------------------------------------
-- 1) RBAC: perfis e usuários
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `roles` (
    `id`        TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `nome`      VARCHAR(30)  NOT NULL,
    `nivel`     TINYINT UNSIGNED NOT NULL COMMENT 'Quanto maior, mais privilégios',
    `descricao` VARCHAR(160) NOT NULL DEFAULT '',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_roles_nome` (`nome`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO `roles` (`id`, `nome`, `nivel`, `descricao`) VALUES
    (1, 'usuario',     10, 'Cria e acompanha as próprias requisições; sincroniza os próprios projetos GitHub'),
    (2, 'admin',       50, 'Visualiza todas as requisições, altera status e consulta todos os logs'),
    (3, 'super-admin', 90, 'Controle total, incluindo exclusão de registros e gestão de usuários');

CREATE TABLE IF NOT EXISTS `usuarios` (
    `id`                BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    `username`          VARCHAR(40)      NOT NULL,
    `nome`              VARCHAR(120)     NOT NULL,
    `email`             VARCHAR(150)     NOT NULL,
    `senha_hash`        VARCHAR(255)     NOT NULL COMMENT 'Hash Werkzeug (PBKDF2/scrypt + salt); nunca texto claro',
    `role_id`           TINYINT UNSIGNED NOT NULL,
    `ativo`             TINYINT(1)       NOT NULL DEFAULT 1,
    `tema`              VARCHAR(20)      NOT NULL DEFAULT 'dark',
    `github_username`   VARCHAR(39)      NULL DEFAULT NULL,
    `tentativas_falhas` TINYINT UNSIGNED NOT NULL DEFAULT 0,
    `bloqueado_ate`     DATETIME         NULL DEFAULT NULL,
    `ultimo_login`      DATETIME         NULL DEFAULT NULL,
    `criado_em`         DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `atualizado_em`     DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_usuarios_username` (`username`),
    UNIQUE KEY `uk_usuarios_email` (`email`),
    KEY `idx_usuarios_role` (`role_id`),
    KEY `idx_usuarios_ativo` (`ativo`),
    CONSTRAINT `fk_usuarios_role` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT `ck_usuarios_tema` CHECK (`tema` IN
        ('dark','dark-pink','dark-green','dark-blue','dark-red','dark-purple'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 2) Requisições e histórico de status (acompanhamento)
--    Status herdados do painel original: registered, pending, approved, partial,
--    rejected, canceled, released, quotation, closed.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `requisicoes` (
    `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `codigo`          VARCHAR(20)     NOT NULL COMMENT 'REQ-AAAA-NNNNNN, gerado pelo servidor',
    `titulo`          VARCHAR(140)    NOT NULL,
    `descricao`       TEXT            NOT NULL,
    `setor`           VARCHAR(30)     NOT NULL,
    `filial`          VARCHAR(40)     NOT NULL,
    `item`            VARCHAR(160)    NOT NULL,
    `quantidade`      DECIMAL(12,3)   NOT NULL DEFAULT 1.000,
    `unidade`         VARCHAR(10)     NOT NULL DEFAULT 'UN',
    `valor_estimado`  DECIMAL(14,2)   NULL DEFAULT NULL,
    `prioridade`      ENUM('baixa','media','alta','critica') NOT NULL DEFAULT 'media',
    `status`          ENUM('registered','pending','approved','partial','rejected',
                           'canceled','released','quotation','closed')
                      NOT NULL DEFAULT 'registered',
    `prazo`           DATE            NULL DEFAULT NULL,
    `referencia`      VARCHAR(60)     NULL DEFAULT NULL,
    `requerente_id`   BIGINT UNSIGNED NOT NULL,
    `responsavel_id`  BIGINT UNSIGNED NULL DEFAULT NULL,
    `criado_em`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `atualizado_em`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_requisicoes_codigo` (`codigo`),
    KEY `idx_requisicoes_status` (`status`),
    KEY `idx_requisicoes_setor` (`setor`),
    KEY `idx_requisicoes_filial` (`filial`),
    KEY `idx_requisicoes_requerente` (`requerente_id`, `criado_em`),
    KEY `idx_requisicoes_responsavel` (`responsavel_id`),
    KEY `idx_requisicoes_criado` (`criado_em`),
    CONSTRAINT `fk_requisicoes_requerente` FOREIGN KEY (`requerente_id`) REFERENCES `usuarios` (`id`)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT `fk_requisicoes_responsavel` FOREIGN KEY (`responsavel_id`) REFERENCES `usuarios` (`id`)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT `ck_requisicoes_quantidade` CHECK (`quantidade` > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `requisicoes_historico` (
    `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `requisicao_id`   BIGINT UNSIGNED NOT NULL,
    `usuario_id`      BIGINT UNSIGNED NULL DEFAULT NULL,
    `acao`            VARCHAR(40)     NOT NULL COMMENT 'criada, editada, status',
    `status_anterior` VARCHAR(20)     NULL DEFAULT NULL,
    `status_novo`     VARCHAR(20)     NULL DEFAULT NULL,
    `comentario`      VARCHAR(500)    NULL DEFAULT NULL,
    `criado_em`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_hist_requisicao` (`requisicao_id`, `criado_em`),
    KEY `idx_hist_usuario` (`usuario_id`),
    CONSTRAINT `fk_hist_requisicao` FOREIGN KEY (`requisicao_id`) REFERENCES `requisicoes` (`id`)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT `fk_hist_usuario` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 3) Portfólio GitHub: repositórios sincronizados e log/auditoria de métricas
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `github_projetos` (
    `id`               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `usuario_id`       BIGINT UNSIGNED NOT NULL COMMENT 'Quem sincronizou',
    `github_username`  VARCHAR(39)     NOT NULL,
    `github_repo_id`   BIGINT UNSIGNED NOT NULL,
    `nome`             VARCHAR(100)    NOT NULL,
    `full_name`        VARCHAR(140)    NOT NULL,
    `descricao`        VARCHAR(500)    NULL DEFAULT NULL,
    `url`              VARCHAR(255)    NOT NULL,
    `linguagem`        VARCHAR(40)     NULL DEFAULT NULL,
    `estrelas`         INT UNSIGNED    NOT NULL DEFAULT 0,
    `forks`            INT UNSIGNED    NOT NULL DEFAULT 0,
    `issues_abertas`   INT UNSIGNED    NOT NULL DEFAULT 0,
    `tamanho_kb`       INT UNSIGNED    NOT NULL DEFAULT 0,
    `commits_recentes` INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT 'Commits públicos recentes (eventos Push)',
    `ultimo_push`      DATETIME        NULL DEFAULT NULL,
    `sincronizado_em`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_github_usuario_repo` (`usuario_id`, `github_repo_id`),
    KEY `idx_github_username` (`github_username`),
    KEY `idx_github_linguagem` (`linguagem`),
    KEY `idx_github_estrelas` (`estrelas`),
    CONSTRAINT `fk_github_projetos_usuario` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `github_metricas_log` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `usuario_id`        BIGINT UNSIGNED NULL DEFAULT NULL,
    `github_username`   VARCHAR(39)     NOT NULL,
    `resultado`         ENUM('ok','erro','rate_limit','nao_encontrado') NOT NULL,
    `total_repos`       INT UNSIGNED    NOT NULL DEFAULT 0,
    `total_estrelas`    INT UNSIGNED    NOT NULL DEFAULT 0,
    `total_forks`       INT UNSIGNED    NOT NULL DEFAULT 0,
    `total_commits`     INT UNSIGNED    NOT NULL DEFAULT 0,
    `resumo`            LONGTEXT        NULL COMMENT 'JSON: linguagens, top repositórios, atividade diária',
    `mensagem`          VARCHAR(300)    NULL DEFAULT NULL,
    `rate_limit_restante` INT           NULL DEFAULT NULL,
    `criado_em`         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_metricas_usuario` (`usuario_id`, `criado_em`),
    KEY `idx_metricas_username` (`github_username`, `criado_em`),
    KEY `idx_metricas_resultado` (`resultado`),
    CONSTRAINT `fk_metricas_usuario` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 4) Controle de concorrência e idempotência (Pilar 4: Idempotência)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `sincronizacao_locks` (
    `chave`     VARCHAR(80) NOT NULL COMMENT 'Identificador do recurso, ex: gh:1:username',
    `expira_em` DATETIME    NOT NULL,
    PRIMARY KEY (`chave`),
    KEY `idx_locks_expira` (`expira_em`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

