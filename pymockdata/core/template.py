import random
import re
import string

import pymockdata.data as mockdata
from pymockdata.core.engine import _get_generator


class TokenParsingError(Exception):
    pass


class Token:
    """This class contains token identifiers that compose a valid template object.

    Attributes:

    DIGIT                       : generates a random digit
    LETTER_LOWER                : generates a lowercase letter
    LETTER_UPPER                : generates an uppercase letter
    LETTER                      : generates a letter (lowercase or uppercase)
    DOT                         : generates a dot
    SYMBOL                      : generates a printable symbol from string.punctuation
    SPACE                       : generates a space
    VALUE(value_id)             : generates a random value from a data set. Data sets are defined in pymockdata.data
        and their IDs are the constants defined in that module
    NUMBER_INTERVAL(min, max)   : generates a random number in the [min, max] interval in decimal representation
    LITERAL(string): generates a string literal. Basically, copies the string parameter into the output.
    """
    _TOKEN_ID_DIGIT = 0
    _TOKEN_ID_LETTER = 1
    _TOKEN_ID_DOT = 2
    _TOKEN_ID_SYMBOL = 3
    _TOKEN_ID_FIELD = 4
    _TOKEN_ID_INTERVAL = 5
    _TOKEN_ID_LITERAL = 6
    _TOKEN_ID_SPACE = 7
    _TOKEN_ID_CUSTOM = 8

    DIGIT = (_TOKEN_ID_DIGIT, None)
    LETTER_LOWER = (_TOKEN_ID_LETTER, "lower")
    LETTER_UPPER = (_TOKEN_ID_LETTER, "upper")
    LETTER = (_TOKEN_ID_LETTER, None)
    DOT = (_TOKEN_ID_DOT, None)
    SYMBOL = (_TOKEN_ID_SYMBOL, None)
    SPACE = (_TOKEN_ID_SPACE, None)

    @classmethod
    def DatasetValue(cls, field_name):
        return cls._TOKEN_ID_FIELD, field_name

    @classmethod
    def NumberInverval(cls, min, max):
        return cls._TOKEN_ID_INTERVAL, (min, max)

    @classmethod
    def Literal(cls, str_literal):
        return cls._TOKEN_ID_LITERAL, str_literal

    @classmethod
    def RandomSymbol(cls, symbol_set):
        return cls._TOKEN_ID_SYMBOL, symbol_set

    @classmethod
    def Custom(cls, custom_func, args=None, kwargs=None):
        return cls._TOKEN_ID_CUSTOM, (custom_func, args, kwargs)

    class Repeat:
        """
        Causes the designated token to repeat multiple times

        Example: (Token.Repeat(Token.DIGIT, 3)) is equivalent to (Token.DIGIT, Token.DIGIT, Token.DIGIT)
        """

        def __init__(self, token, repeat=1, random_repeat=None):
            self._token = token
            if random_repeat:
                self._repeat = random.randint(random_repeat[0], random_repeat[1])
            else:
                self._repeat = repeat

        def get(self):
            return [self._token for _ in range(self._repeat)]

    class Generator:
        """
        Causes the token to be resolved by using a generator identified by the generator_id ID.

        For example, Token.Generator("male_name") will resolve to MaleNameGenerator().generate() because
            MaleNameGenerator.ID == "male_name")
        """

        def __init__(self, generator_id):
            self._generator_id = generator_id

        def get(self):
            generator = _get_generator(self._generator_id)
            if generator:
                return generator().generate()

            raise TokenParsingError("No suitable generator found for ID={}".format(self._generator_id))

    class Transform:
        """
        Causes the token to be resolved by applying a template function to the wrapped token.

        For example, `Token.Transform(Token.LITERAL("hello world"), template=lambda x: x.upper())` will resolve to
            `"HELLO WORLD"` (`lambda x: x.upper()` will be applied to the `Token.LITERAL(...)` token).
        """

        def __init__(self, token, template):
            self.wrapped_token = token
            self.template = template

    class Choice:
        """
        Returns random tokens from a token set.
        """

        def __init__(self, *tokens, count=None, count_range=None):
            """
            :param tokens: The token set
            :param count: The count of the final set. Can be greater than len(tokens). Has priority over count_range
            :param count_range: A (min, max) tuple. Will generate a random amount of tokens, from min instances to max.
            """
            self._tokens = tokens
            if count:
                self._count_min = count
                self._count_max = count
            elif count_range:
                self._count_min = count_range[0]
                self._count_max = count_range[1]
            else:
                self._count_min = 1
                self._count_max = 1

        def get(self):
            x = [random.choice(self._tokens) for _ in range(random.randint(self._count_min, self._count_max))]
            return x

    class Metadata:
        """
        Sets a template internal value to be used by other Tokens. Can be used to generate realistic looking sets
        of data. For example, one can use the template

        t = Template(
            Token.BaseValue("base_name", Token.Generator('full_name')),
            Token.BaseValue("base_domain", Token.Generator('domain')),
            Token.ValueTransform("base_name", lambda x: x),
            Token.LITERAL(" ; "),
            Token.BaseValueTransform(["base_name", "base_domain"], lambda x, y: re.sub("[ -.]", "", x).lower() + "@" + y)
        )

        to generate pairs of full_name and emails that match:
        Franklin Berry ; franklinberry@tasty.io
        Hayden Anahi J. Melton ; haydenanahijmelton@ink.io
        Molly Booker ; mollybooker@territory.biz

        This Token will not resolve in the final output, it is only used internally.
        """

        def __init__(self, identifier, token):
            self.token = token
            self.identifier = identifier

        def get(self):
            return self.token

    class BaseValueTransform:


        def __init__(self, identifiers, template):
            if not isinstance(identifiers, list):
                identifiers = [identifiers]
            self.identifiers = identifiers
            self._template = template

        def get(self, *base_values):
            if len(base_values) == 1:
                return self._template(base_values[0])
            return self._template(*base_values)


class Template:
    def __init__(self, *tokens):
        self._tokens = tokens
        self._base_values = {}

    def render(self, *, seed=None):
        if seed:
            random.seed(seed)

        parsed_tokens = []
        for token in self._tokens:
            parsed_tokens.append(self._resolve_token(token))

        return "".join(parsed_tokens)

    def _resolve_token(self, token):
        if isinstance(token, (Token.Repeat, Token.Transform, Token.Generator, Token.Choice,
                              Token.Metadata, Token.BaseValueTransform)):
            return self._resolve_token_wrapper(token)
        else:
            return self._resolve_simple_token(token)

    def _resolve_simple_token(self, token):
        token_id, token_data = token
        return self._token_resolvers[token_id](self, token_data)

    def _resolve_token_wrapper(self, token_wrapper):
        parsed_tokens = []
        if isinstance(token_wrapper, Token.Repeat):
            for subtoken in token_wrapper.get():
                parsed_tokens.append(self._resolve_token(subtoken))
        elif isinstance(token_wrapper, Token.Generator):
            parsed_tokens.append(token_wrapper.get())
        elif isinstance(token_wrapper, Token.Transform):
            parsed_tokens.append(token_wrapper.template(self._resolve_token(token_wrapper.wrapped_token)))
        elif isinstance(token_wrapper, Token.Choice):
            for subtoken in token_wrapper.get():
                parsed_tokens.append(self._resolve_token(subtoken))
        elif isinstance(token_wrapper, Token.Metadata):
            self._base_values[token_wrapper.identifier] = self._resolve_token(token_wrapper.token)
        elif isinstance(token_wrapper, Token.BaseValueTransform):
            base_values = []
            for identifier in token_wrapper.identifiers:
                if identifier not in self._base_values:
                    raise TokenParsingError(
                        "Base value identifier '{}' referenced before definition".format(token_wrapper.identifiers))
                base_values.append(self._base_values[identifier])
            parsed_tokens.append(token_wrapper.get(*base_values))
        return "".join(parsed_tokens)

    def _token_digit_resolver(self, token_data):
        return random.choice(string.digits)

    def _token_letter_resolver(self, token_data):
        if token_data == "upper":
            return random.choice(string.ascii_uppercase)
        elif token_data == "lower":
            return random.choice(string.ascii_lowercase)
        else:
            return random.choice(string.ascii_letters)

    def _token_symbol_resolver(self, token_data):
        if token_data:
            return random.choice(token_data)
        else:
            return random.choice(string.punctuation)

    def _token_field_resolver(self, token_data):
        if not hasattr(mockdata, token_data):
            raise TokenParsingError("field '{}' does not exist in pymockdata.data".format(token_data))
        return random.choice(getattr(mockdata, token_data))

    def _token_interval_resolver(self, token_data):
        return str(random.randint(token_data[0], token_data[1]))

    def _token_literal_resolver(self, token_data):
        return token_data

    def _token_point_resolver(self, token_data):
        return "."

    def _token_space_resolver(self, token_data):
        return " "

    def _token_custom_resolver(self, token_data):
        func, args, kwargs = token_data
        if not args:
            args = []
        if not kwargs:
            kwargs = {}

        return func(*args, **kwargs)

    _token_resolvers = {
        Token._TOKEN_ID_DIGIT: _token_digit_resolver,
        Token._TOKEN_ID_LETTER: _token_letter_resolver,
        Token._TOKEN_ID_DOT: _token_point_resolver,
        Token._TOKEN_ID_SYMBOL: _token_symbol_resolver,
        Token._TOKEN_ID_FIELD: _token_field_resolver,
        Token._TOKEN_ID_INTERVAL: _token_interval_resolver,
        Token._TOKEN_ID_LITERAL: _token_literal_resolver,
        Token._TOKEN_ID_SPACE: _token_space_resolver,
        Token._TOKEN_ID_CUSTOM: _token_custom_resolver,
    }


if __name__ == '__main__':
    t = Template(
        Token.Metadata("base_name", Token.Generator('full_name')),
        Token.Metadata("base_domain", Token.Generator('domain')),
        Token.BaseValueTransform("base_name", lambda x: x),
        Token.Literal(" ; "),
        Token.BaseValueTransform(["base_name", "base_domain"], lambda x, y: re.sub("[ -.]", "", x).lower() + "@" + y),
    )

    print(t.render())
