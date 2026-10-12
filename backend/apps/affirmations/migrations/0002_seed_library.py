from django.db import migrations


def seed(apps, schema_editor):
    from apps.affirmations.library import LIBRARY

    Affirmation = apps.get_model("affirmations", "Affirmation")
    existing = set(Affirmation.objects.filter(owner__isnull=True).values_list("text", flat=True))
    Affirmation.objects.bulk_create(
        [Affirmation(text=t, category=c) for c, items in LIBRARY.items() for t in items if t not in existing],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [("affirmations", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
