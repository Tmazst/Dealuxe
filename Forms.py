
from flask_wtf import FlaskForm
from wtforms import StringField,PasswordField,SubmitField, TextAreaField,BooleanField, SelectField,DateField, URLField, RadioField, HiddenField, TelField, MultipleFileField,IntegerField,SelectMultipleField, FloatField
from wtforms.validators import DataRequired,Length,Email, EqualTo, ValidationError, Optional
from flask_login import current_user
from flask_wtf.file import FileField , FileAllowed
from wtforms.widgets import ListWidget, CheckboxInput
# from app import db, User
import re

class NormalizedPhoneField(TelField):
    def process_formdata(self, valuelist):
        if valuelist:
            # Normalize the number here before validation
            self.data = valuelist[0].replace(" ", "").replace("-", "")



class RegistrationForm(FlaskForm):

    username = HiddenField(validators=[DataRequired()])
    name = StringField("Name",validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField("Email",validators=[DataRequired(), Email()])
    phone = NormalizedPhoneField("Phone Number",validators=[DataRequired()])
    password = PasswordField("Password",validators=[DataRequired()])
    country = SelectField(choices=[
        ('Eswatini', 'Eswatini'), ('South Africa', 'South Africa'),
        ('Lesotho', 'Lesotho'), ('Mozambique', 'Mozambique'),
        ('Namibia', 'Namibia'), ('Botswana', 'Botswana'),
        ('Zimbabwe', 'Zimbabwe'), ('Malawi', 'Malawi'),
    ])
    submit = SubmitField('Proceed To Game')

class GameStartForm(FlaskForm):

    choose_opponent = SelectField(choices=[
        ('AI_Robot', 'AI Robot'), ('Live_Game', 'Live Game')
    ])
    cards_number = SelectField(choices=[
        (6, '6'), (6, '8'),(10, '10')
    ])
    bet_or_free=RadioField(
        choices=[
        ('bet', 'bet'), ('free', 'free')
        ]
    )
    bet_amount=FloatField("Bet Amount")
    freegame_fake_bet=FloatField("Free Bet Amount")

    submit = SubmitField('Start Game')