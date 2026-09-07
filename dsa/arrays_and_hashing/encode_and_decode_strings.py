"""
Encode and Decode Strings [Medium]

Design an algorithm to encode a list of strings to a single string. The encoded string is then decoded back to the original list of strings.
Please implement encode and decode

Example 1:
Input: ["neet","code","love","you"]
Output:["neet","code","love","you"]

Example 2:
Input: ["we","say",":","yes"]
Output: ["we","say",":","yes"]

Constraints:
0 <= strs.length < 100
0 <= strs[i].length < 200
strs[i] contains only UTF-8 characters.

You should aim for a solution with O(m) time for each encode() and decode() call and O(m+n) space, where m is the sum of lengths of all the strings and n is the number of strings.
"""


def encode(input: list[str]) -> str:
    out: str = ""
    if len(input) == 0:
        return out
    sizes: list[int] = []
    for word in input:
        sizes.append(len(word))
        out += word
    pretext: str = ",".join([str(s) for s in sizes])
    return f"{pretext}#{out}"


def decode(input: str) -> list[str]:
    out: list[str] = []
    if input == "":
        return out
    sizes: list[int] = []
    size: str = ""
    text: str = ""
    for i, ch in enumerate(input):
        if ch == "#":
            sizes.append(int(size))
            text: str = input[i+1:]
            break
        elif ch == ",":
            sizes.append(int(size))
            size = ""
        else:
            size += ch
    assert sum(sizes) == len(text), "sizes don't add up to text len!"
    for wordlen in sizes:
        out.append(text[:wordlen])
        text = text[wordlen:]
    return out


def test() -> None:
    assert decode(encode(["neet","code","love","you"])) == ["neet","code","love","you"], "Case 1 failed!"
    assert decode(encode(["we","say",":","yes"])) == ["we","say",":","yes"], "Case 2 failed!"
    assert decode(encode([])) == [], "Case 3 failed!"
    assert decode(encode([''])) == [''], "Case 4 failed!"
    assert decode(encode(['', ''])) == ['', ''], "Case 5 failed!"
    print("All tests passed!")


if __name__ == "__main__":
    test()
