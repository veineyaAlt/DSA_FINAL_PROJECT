-- ============================================================
-- Secret Santa — реляционная схема (SQLite 3)
-- membership устраняет связь M:N USER<->GROUP; wish/exclusion/assignment
-- ссылаются на составной PK membership(group_id,user_id); feedback 1:0..1 к assignment.
-- Схема нормализована до 3NF (описание см. в proposal-документе).
-- ============================================================
PRAGMA foreign_keys = ON;

-- 1. USER — участник/организатор
CREATE TABLE users (
    user_id        INTEGER      PRIMARY KEY,
    email          TEXT         NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT         NOT NULL,
    display_name   TEXT         NOT NULL,
    created_at     TEXT         NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- 2. GROUP — комната обмена подарками
CREATE TABLE groups (
    group_id       INTEGER      PRIMARY KEY,
    organizer_id   INTEGER      NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    group_name     TEXT         NOT NULL CHECK(length(group_name) BETWEEN 3 AND 80),
    event_date     TEXT         NOT NULL,
    join_deadline  TEXT         NOT NULL,
    budget_hint    INTEGER      CHECK(budget_hint IS NULL OR budget_hint > 0),
    join_code      TEXT         NOT NULL UNIQUE,
    status         TEXT         NOT NULL DEFAULT 'open'
                   CHECK(status IN ('open','drawn','closed')),
    CHECK(join_deadline <= event_date)
);

-- 3. MEMBERSHIP — резолвер M:N (USER <-> GROUP), сплошной ключ
CREATE TABLE membership (
    group_id   INTEGER  NOT NULL REFERENCES groups(group_id) ON DELETE CASCADE,
    user_id    INTEGER  NOT NULL REFERENCES users(user_id)    ON DELETE CASCADE,
    joined_at  TEXT     NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (group_id, user_id)
);

-- 4. WISH — список желаемого участника в конкретной группе
CREATE TABLE wishes (
    wish_id     INTEGER  PRIMARY KEY,
    group_id    INTEGER  NOT NULL,
    user_id     INTEGER  NOT NULL,
    wish_title  TEXT     NOT NULL,
    wish_url    TEXT,
    wish_note   TEXT,
    priority    INTEGER  NOT NULL DEFAULT 2 CHECK(priority BETWEEN 1 AND 3),
    created_at  TEXT     NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (group_id, user_id)
        REFERENCES membership(group_id, user_id) ON DELETE CASCADE
);

-- 5. EXCLUSION — «не дарить пользователю X» (парные запреты)
CREATE TABLE exclusions (
    exclusion_id   INTEGER  PRIMARY KEY,
    group_id       INTEGER  NOT NULL,
    user_id        INTEGER  NOT NULL,
    target_user_id INTEGER  NOT NULL,
    reason         TEXT,
    CHECK (user_id <> target_user_id),
    UNIQUE (group_id, user_id, target_user_id),
    FOREIGN KEY (group_id, user_id)
        REFERENCES membership(group_id, user_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id, target_user_id)
        REFERENCES membership(group_id, user_id) ON DELETE CASCADE
);

-- 6. ASSIGNMENT — результат жеребьевки: кто кому дарит в группе
CREATE TABLE assignments (
    assignment_id  INTEGER  PRIMARY KEY,
    group_id       INTEGER  NOT NULL,
    giver_id       INTEGER  NOT NULL,
    receiver_id    INTEGER  NOT NULL,
    secret_code    TEXT     NOT NULL UNIQUE,
    drawn_at       TEXT     NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (giver_id <> receiver_id),
    UNIQUE (group_id, giver_id),      -- каждый дарит ровно 1 раз
    UNIQUE (group_id, receiver_id),   -- каждый получает ровно 1 раз
    FOREIGN KEY (group_id, giver_id)
        REFERENCES membership(group_id, user_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id, receiver_id)
        REFERENCES membership(group_id, user_id) ON DELETE CASCADE
);

-- 7. FEEDBACK — отзыв дателя о подарке (1:0..1 к assignment)
CREATE TABLE feedback (
    feedback_id    INTEGER  PRIMARY KEY,
    assignment_id  INTEGER  NOT NULL UNIQUE
                   REFERENCES assignments(assignment_id) ON DELETE CASCADE,
    rating         INTEGER  NOT NULL CHECK(rating BETWEEN 1 AND 5),
    comment        TEXT,
    created_at     TEXT     NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Индексы под основные запросы
CREATE INDEX idx_users_email      ON users(email);
CREATE INDEX idx_groups_status    ON groups(status, event_date);
CREATE INDEX idx_groups_org       ON groups(organizer_id);
CREATE INDEX idx_membership_user  ON membership(user_id);
CREATE INDEX idx_wishes_gu        ON wishes(group_id, user_id);
CREATE INDEX idx_wishes_receiver  ON wishes(group_id, user_id, priority);
CREATE INDEX idx_excl_gu          ON exclusions(group_id, user_id);
CREATE INDEX idx_assign_giver     ON assignments(group_id, giver_id);
CREATE INDEX idx_feedback_assign  ON feedback(assignment_id);

-- VIEW: открытые группы с числом участников и желаний
CREATE VIEW view_open_groups AS
SELECT
    g.group_id,
    g.group_name,
    g.event_date,
    g.join_deadline,
    g.budget_hint,
    COUNT(DISTINCT m.user_id)  AS member_count,
    COUNT(w.wish_id)           AS wish_count
FROM groups g
LEFT JOIN membership m ON m.group_id = g.group_id
LEFT JOIN wishes    w ON w.group_id = g.group_id AND w.user_id = m.user_id
WHERE g.status = 'open'
GROUP BY g.group_id;

-- VIEW: сводный отчёт по отзывам (Q6): средняя оценка и количество по каждой группе
CREATE VIEW view_gift_reports AS
SELECT
    g.group_id,
    g.group_name,
    g.event_date,
    COUNT(f.feedback_id)          AS reviews_count,
    ROUND(AVG(f.rating), 2)       AS avg_rating
FROM groups g
JOIN assignments a ON a.group_id = g.group_id
JOIN feedback    f ON f.assignment_id = a.assignment_id
GROUP BY g.group_id;
