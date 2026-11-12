test = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]

#for item in test:
#    print(item)
#    if item < 12 and item >6:
#        print("Hallo")
#    elif item > 3:
#        print("Hallo2")
#    else:
#        print("Hallo3")
        
x = 432282882191020391230123912032193094320543065479450321043455460506430560093218592830174893287998723987239872138732987238973298732987
y = 0
while x > 1:
    if not x % 2:
        x /= 2
    else:
        x *= 3
        x += 1
    y += 1
print(y)
