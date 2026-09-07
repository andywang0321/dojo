# AQR: Given two lists X and Y, return their correlation.


def mean(A: list) -> float:
    return sum(A) / len(A)


def hadamard_product(A: list, B: list) -> list:
    return [a * b for (a, b) in zip(A, B)]


def correlation(X: list, Y: list) -> float:
    XX = hadamard_product(X, X)
    YY = hadamard_product(Y, Y)
    XY = hadamard_product(X, Y)

    EX = mean(X)
    EY = mean(Y)
    EXX = mean(XX)
    EYY = mean(YY)
    EXY = mean(XY)

    return (EXY - EX * EY) / ((EXX - EX**2) ** 0.5 * (EYY - EY**2) ** 0.5)


def main() -> None:
    X: list = [1, 2, 3, 4, 5]
    Y: list = [3, 2, 5, 9, 6]
    assert correlation(X, Y) - 0.7506 < 1e-5, "Case failed!"
    print("All tests passed!")


if __name__ == "__main__":
    main()
