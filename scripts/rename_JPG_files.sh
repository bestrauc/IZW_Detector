# rename from the 'Something ([0-9]+).JPG' format to Something_[0-9]+.jpg
# remove -n for actual execution
rename -n 's/.*\((\d+)\).*\.(JPG|jpg)/sprintf("Leopard_%06d.jpg", $1)/e' *

