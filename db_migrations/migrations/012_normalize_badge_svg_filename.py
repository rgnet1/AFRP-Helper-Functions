"""
Migration 012: Normalize badge_template svg_filename to built-in template

All templates now use the shipped minimal_badge_landscape.svg; user uploads
are no longer supported.
"""


def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE badge_template SET svg_filename = 'minimal_badge_landscape.svg'"
    )
    conn.commit()
    print("  ✓ Normalized badge_template.svg_filename to minimal_badge_landscape.svg")


def downgrade(conn):
    print("  ℹ Manual rollback required: svg_filename values cannot be restored")
