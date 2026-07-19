def calculate_average(numbers):
    total = 0
    for i in range(len(numbers)):
        total = total + numbers[i]
    average = total / len(numbers)
    return average

def find_max(lst):
    max = lst[0]
    for item in lst:
        if item > max:
            max = item
    return max
