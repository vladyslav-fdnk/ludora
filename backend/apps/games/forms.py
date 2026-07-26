import csv
import io
from dataclasses import dataclass

from django import forms
from django.core.validators import FileExtensionValidator


@dataclass(frozen=True)
class LicenseKeyCSVImport:
    values: list[str]
    empty_row_count: int


class LicenseKeyCSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV file",
        validators=[FileExtensionValidator(allowed_extensions=("csv",))],
    )

    def clean_csv_file(self):
        uploaded_file = self.cleaned_data["csv_file"]

        try:
            content = uploaded_file.read().decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise forms.ValidationError("Upload a valid UTF-8 CSV file.") from error

        try:
            rows = csv.reader(io.StringIO(content), strict=True)
            header = next(rows, None)
            if header is None or "value" not in header:
                raise forms.ValidationError(
                    'The CSV file must include a header with a "value" column.'
                )

            value_index = header.index("value")
            values = []
            empty_rows = 0
            for row in rows:
                value = row[value_index].strip() if len(row) > value_index else ""
                if not value:
                    empty_rows += 1
                    continue
                values.append(value)
        except csv.Error as error:
            raise forms.ValidationError(f"Upload a valid CSV file: {error}.") from error

        return LicenseKeyCSVImport(values=values, empty_row_count=empty_rows)
