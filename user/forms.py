"""
User account forms: profile editing and KYC / ID photo uploads.
"""
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SelectField, DateField, SubmitField
from wtforms.validators import Optional, Length

from Forms import NormalizedPhoneField


COUNTRY_CHOICES = [
    ('', 'Select country'),
    ('Eswatini', 'Eswatini'),
    ('South Africa', 'South Africa'),
    ('Lesotho', 'Lesotho'),
    ('Mozambique', 'Mozambique'),
    ('Namibia', 'Namibia'),
    ('Botswana', 'Botswana'),
    ('Zimbabwe', 'Zimbabwe'),
    ('Malawi', 'Malawi'),
]

IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg']
KYC_EXTENSIONS = ['png', 'jpg', 'jpeg', 'pdf']


class ProfileForm(FlaskForm):
    """Editable profile fields (username + email stay read-only)."""
    full_name = StringField('Full Name', validators=[Optional(), Length(max=100)])
    phone = NormalizedPhoneField('Phone Number', validators=[Optional(), Length(max=20)])
    country = SelectField('Country', choices=COUNTRY_CHOICES, validators=[Optional()])
    address = StringField('Address', validators=[Optional(), Length(max=200)])
    date_of_birth = DateField('Date of Birth', validators=[Optional()])
    id_number = StringField('ID / Passport Number', validators=[Optional(), Length(max=50)])
    submit = SubmitField('Save Changes')


class KYCDocumentForm(FlaskForm):
    """Upload a KYC document (proof of address / utility bill)."""
    kyc_document = FileField(
        'KYC Document (proof of address / utility bill)',
        validators=[
            FileAllowed(KYC_EXTENSIONS, 'Images (png/jpg) or PDF only'),
        ],
    )
    submit = SubmitField('Upload KYC Document')


class IDPhotoForm(FlaskForm):
    """Upload ID / passport photos (front and back)."""
    id_photo = FileField(
        'ID / Passport Photo (front)',
        validators=[FileAllowed(IMAGE_EXTENSIONS, 'Images (png/jpg) only')],
    )
    id_photo_back = FileField(
        'ID / Passport Photo (back)',
        validators=[FileAllowed(IMAGE_EXTENSIONS, 'Images (png/jpg) only')],
    )
    submit = SubmitField('Upload ID Photos')
