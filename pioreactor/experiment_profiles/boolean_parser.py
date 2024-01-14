from .sly import Lexer
from .sly import Parser

from pioreactor.pubsub import subscribe
from pioreactor.whoami import get_latest_experiment_name

class BoolLexer(Lexer):
    tokens = { NAME, AND, OR, NOT, EQUAL, LESS_THAN, GREATER_THAN, NUMBER, UNIT_JOB_SETTING }
    ignore = ' \t'

    # Tokens
    UNIT_JOB_SETTING = r"[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*'"

    NAME = r'[a-zA-Z_][a-zA-Z0-9_]*'
    NAME['and'] = AND
    NAME['or'] = OR
    NAME['not'] = NOT

    # Comparison Operators
    LESS_THAN = r'<'
    EQUAL = r'='
    GREATER_THAN = r'>'

    NUMBER = r"[+-]?([0-9]*[.])?[0-9]+" # decimal number

    # Special symbols
    literals = { '(', ')' }

class BoolParser(Parser):
    tokens = BoolLexer.tokens

    precedence = (
        ('left', AND, OR),
        ('right', NOT),
        ('nonassoc', LESS_THAN, EQUAL, GREATER_THAN),
    )

    @_('expr AND expr',
       'expr OR expr')
    def expr(self, p):
        if p[1] == 'and':
            return p.expr0 and p.expr1
        elif p[1] == 'or':
            return p.expr0 or p.expr1

    @_('expr LESS_THAN expr',
       'expr EQUAL expr',
       'expr GREATER_THAN expr')
    def expr(self, p):
        if p[1] == '<':
            return p.expr0 < p.expr1
        elif p[1] == '=':
            return p.expr0 == p.expr1
        elif p[1] == '>':
            return p.expr0 > p.expr1

    @_('NOT expr')
    def expr(self, p):
        return not p.expr

    @_('NAME')
    def expr(self, p):
        if p.NAME == 'True':
            return True
        elif p.NAME == 'False':
            return False
        else:
            raise SyntaxError(p.NAME)

    @_('"(" expr ")"')
    def expr(self, p):
        return p.expr

    @_('NUMBER')
    def expr(self, p):
        return float(p.NUMBER)

    @_('UNIT_JOB_SETTING')
    def expr(self, p) -> float:
        unit, job, setting = p.UNIT_JOB_SETTING.split(".")
        experiment = get_latest_experiment_name()
        result = subscribe(f"pioreactor/{unit}/{experiment}/{job}/{setting}")

        if result:
            # error handling here
            return float(result.payload)
        else:
            return None


def parse_profile_if_directive_to_bool(directive: str) -> bool:
    lexer = BoolLexer()
    parser = BoolParser()
    return parser.parse(lexer.tokenize(directive))