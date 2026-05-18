-- Migration 014: Internal admin access control.

CREATE TABLE IF NOT EXISTS admin_users (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'admin',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'admin_users_role_check'
    ) THEN
        ALTER TABLE admin_users
            ADD CONSTRAINT admin_users_role_check
            CHECK (role IN ('owner', 'admin', 'operator'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_admin_users_email
    ON admin_users(lower(email));

INSERT INTO admin_users (user_id, email, role)
SELECT id, email, 'owner'
FROM auth.users
WHERE lower(email) = lower('akramkazimovbrand@gmail.com')
ON CONFLICT (user_id) DO UPDATE
SET email = EXCLUDED.email,
    role = EXCLUDED.role,
    updated_at = now();
