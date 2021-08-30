import io
import sys
from collections import namedtuple

# Token types
CHAR = 1
SPEC = 2
SPACE = 3
NEWLINE = 4
EOF = -1
UNREC = -2

Token = namedtuple("Token", ["type", "spelling"])


def is_ascii(s):
    return all(ord(c) < 128 for c in s)


class TokenScanner:
    SPECIAL = {"<", ">", "(", ")", "[", "]", "\\", ".", ",", ";", ":", "@", "\""}

    def __init__(self, instream):
        self.instream = instream
        self.current = self.read_token()

    def accept(self, token_type=0, spelling=None):
        acceptable = True
        if token_type != 0 and token_type != self.current.type:
            acceptable = False
        if spelling and spelling != self.current.spelling:
            acceptable = False
        if acceptable:
            self.current = self.read_token()
        return acceptable

    def read_token(self):
        next_char = self.instream.read(1)
        if not next_char:
            return Token(EOF, "\0")
        if next_char == "\t" or next_char == " ":
            return Token(SPACE, next_char)
        if next_char == "\n":
            return Token(NEWLINE, next_char)
        if next_char in TokenScanner.SPECIAL:
            return Token(SPEC, next_char)
        if is_ascii(next_char):
            return Token(CHAR, next_char)
        return Token(UNREC, next_char)


class ParseException(BaseException):

    def __init__(self, symbol):
        BaseException.__init__(self, "ERROR -- %s" % symbol)


def accept_literal_str(scanner, string):
    for s in string:
        if not scanner.accept(spelling=s):
            return False
    return True


def parse_mail_from_cmd(scanner):
    if not accept_literal_str(scanner, "MAIL"):
        raise ParseException("mail-from-cmd")

    parse_whitespace(scanner)

    if not accept_literal_str(scanner, "FROM:"):
        raise ParseException("mail-from-cmd")

    parse_nullspace(scanner)
    parse_path(scanner)
    parse_nullspace(scanner)
    if not scanner.accept(NEWLINE):
        raise ParseException("mail-from-cmd")


def parse_whitespace(scanner):
    if not scanner.accept(SPACE):
        raise ParseException("whitespace")
    while scanner.current.type == SPACE:
        scanner.accept(SPACE)


def parse_nullspace(scanner):
    if scanner.current.type == SPACE:
        parse_whitespace(scanner)


def parse_path(scanner):
    if not scanner.accept(SPEC, "<"):
        raise ParseException("path")
    parse_mailbox(scanner)
    if not scanner.accept(SPEC, ">"):
        raise ParseException("path")


def parse_mailbox(scanner):
    parse_string(scanner)
    if not scanner.accept(SPEC, "@"):
        raise ParseException("mailbox")
    parse_domain(scanner)


def parse_string(scanner):
    if not scanner.accept(CHAR):
        raise ParseException("string")
    while scanner.current.type == CHAR:
        scanner.accept(CHAR)


def parse_domain(scanner):
    parse_element(scanner)
    if scanner.current.type == SPEC and scanner.current.spelling == ".":
        scanner.accept(SPEC, ".")
        parse_domain(scanner)


def accept_letter(scanner):
    if scanner.current.type == CHAR and scanner.current.spelling.isalpha():
        scanner.accept(CHAR, scanner.current.spelling)
        return True
    return False


def parse_element(scanner):
    if not accept_letter(scanner):
        raise ParseException("element")

    if not scanner.current.type == CHAR:
        return
    if scanner.current.spelling.isalpha() or scanner.current.spelling.isdigit():
        parse_letter_digit_string(scanner)


def parse_letter_digit_string(scanner):
    parse_letter_digit(scanner)

    if not scanner.current.type == CHAR:
        return
    while scanner.current.spelling.isalpha() or scanner.current.spelling.isdigit():
        parse_letter_digit(scanner)


def parse_letter_digit(scanner):
    if scanner.current.type != CHAR:
        raise ParseException("let-dig")
    if scanner.current.spelling.isalpha() or scanner.current.spelling.isdigit():
        scanner.accept(CHAR, scanner.current.spelling)
    else:
        raise ParseException("let_dig")


if __name__ == "__main__":
    for line in sys.stdin:
        print(line, end="")
        stream = io.StringIO(line)
        tok_scanner = TokenScanner(stream)
        try:
            parse_mail_from_cmd(tok_scanner)
            print("Sender ok")
        except ParseException as e:
            print(e.args[0])
