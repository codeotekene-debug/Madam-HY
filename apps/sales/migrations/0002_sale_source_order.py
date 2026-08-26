from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
        ('sales', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='source_order',
            field=models.OneToOneField(
                blank=True,
                help_text='Customer order converted into this sale, when applicable.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sale',
                to='orders.order',
            ),
        ),
    ]