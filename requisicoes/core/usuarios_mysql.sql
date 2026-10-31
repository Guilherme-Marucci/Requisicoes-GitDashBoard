-- =============================================================================
-- Script DDL MySQL: Subsistema de Autenticação e Ciclo de Vida de Credenciais
-- Banco de Dados: sistema_login | Tabela: usuarios
-- Compatível com a estrutura corporativa Supersonic (S/N e colunas de tokens)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS `sistema_login`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `sistema_login`;

CREATE TABLE IF NOT EXISTS `usuarios` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `nome` VARCHAR(120) NOT NULL DEFAULT '',
    `email` VARCHAR(150) NOT NULL,
    `senha_hash` VARCHAR(255) NOT NULL,
    `criado_em` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `DT_ALT` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Flags corporativas de status e permissões ('S' = Sim / Ativo, 'N' = Não / Inativo)
    `ATIVO` CHAR(1) NOT NULL DEFAULT 'N',
    `EMAIL_VERIFICADO` CHAR(1) NOT NULL DEFAULT 'N',
    `ADM` CHAR(1) NOT NULL DEFAULT 'N',
    `ADM_WMS` CHAR(1) NOT NULL DEFAULT 'N',
    `ADM_SAC` CHAR(1) NOT NULL DEFAULT 'N',
    `ADM_CONT` CHAR(1) NOT NULL DEFAULT 'N',
    `ADM_MAN` CHAR(1) NOT NULL DEFAULT 'N',
    `acesso_comp` CHAR(1) NOT NULL DEFAULT 'N',

    -- Dados complementares corporativos e vínculo Rodopar
    `telefone` VARCHAR(30) NULL DEFAULT NULL,
    `ACESSOS` VARCHAR(255) NULL DEFAULT NULL,
    `telegram_id` VARCHAR(64) NULL DEFAULT NULL,
    `USUARIO_RODOPAR` VARCHAR(60) NULL DEFAULT NULL,
    `login_comp` VARCHAR(60) NULL DEFAULT NULL,
    `filial` VARCHAR(20) NULL DEFAULT NULL,

    -- Ciclo de vida do Token de Ativação / Verificação de E-mail (validade: 24 horas)
    `TOKEN_EMAIL` VARCHAR(128) NULL DEFAULT NULL,
    `TOKEN_EMAIL_EXPIRA` DATETIME NULL DEFAULT NULL,

    -- Ciclo de vida do Token de Recuperação / Reset de Senha (validade: 20 minutos, uso único)
    `reset_token` VARCHAR(128) NULL DEFAULT NULL,
    `token_expiracao` DATETIME NULL DEFAULT NULL,

    -- Colunas espelho da especificação canônica (mantidas sincronizadas pelo core/auth.py quando presentes)
    `token_verificacao` VARCHAR(128) GENERATED ALWAYS AS (`TOKEN_EMAIL`) VIRTUAL,
    `token_verificacao_expira` DATETIME GENERATED ALWAYS AS (`TOKEN_EMAIL_EXPIRA`) VIRTUAL,
    `token_recuperacao` VARCHAR(128) GENERATED ALWAYS AS (`reset_token`) VIRTUAL,
    `token_recuperacao_expira` DATETIME GENERATED ALWAYS AS (`token_expiracao`) VIRTUAL,
    `atualizado_em` DATETIME GENERATED ALWAYS AS (`DT_ALT`) VIRTUAL,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_usuarios_email` (`email`),
    KEY `idx_usuarios_email` (`email`),
    KEY `idx_usuarios_token_email` (`TOKEN_EMAIL`),
    KEY `idx_usuarios_reset_token` (`reset_token`),
    KEY `idx_usuarios_nome` (`nome`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
