ALTER TABLE resume_projects
    ADD COLUMN project_background text,
    ADD COLUMN project_responsibilities text[] NOT NULL DEFAULT '{}',
    ADD COLUMN project_outcomes text[] NOT NULL DEFAULT '{}',
    ADD COLUMN architecture_score smallint
        CHECK (architecture_score BETWEEN 1 AND 10),
    ADD COLUMN architecture_reason text,
    ADD COLUMN credibility_score smallint
        CHECK (credibility_score BETWEEN 1 AND 10),
    ADD COLUMN credibility_reason text,
    ADD COLUMN embellishment_risk_score smallint
        CHECK (embellishment_risk_score BETWEEN 1 AND 10),
    ADD COLUMN embellishment_risk_reason text,
    ADD COLUMN overall_score numeric(3,1)
        GENERATED ALWAYS AS (
            round(
                (
                    architecture_score
                    + credibility_score
                    + (11 - embellishment_risk_score)
                )::numeric / 3,
                1
            )
        ) STORED;
