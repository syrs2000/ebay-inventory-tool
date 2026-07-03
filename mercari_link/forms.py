from django import forms


class MercariCSVImportForm(forms.Form):
    csv_file = forms.FileField(label="CSVファイル")
