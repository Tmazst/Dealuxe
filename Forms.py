
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

    choose_opponent = SelectField('Choose Opponent', choices=[
        ('ai', 'AI Robot'), ('Live_Game', 'Live Game')
    ])
    cards_number = SelectField('Number of Cards', choices=[
        ('6', '6'), ('8', '8'),('10', '10')
    ])
    bet_or_free=RadioField('Bet Type',
        choices=[
        ('bet', 'Real Money Bet (Coming Soon)'), ('fake', 'Awarded Money Bet')
        ],
        default='fake'
    )
    bet_amount=FloatField("Real Bet Amount (SZL)")
    freegame_fake_bet=FloatField("Fake Bet Amount (SZL)")

    submit = SubmitField('Start Game')
