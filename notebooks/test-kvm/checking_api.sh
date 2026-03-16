#!/bin/bash

BASE_URL="http://10.128.0.4:9080/kx"
HEADERS=(-H "Content-Type: application/json")
TIMEOUT=(--connect-timeout 10 --max-time 20)

echo "🔌 Connecting to KVM..."
curl -X POST "${BASE_URL}/connect" "${HEADERS[@]}" -d '{}' -i "${TIMEOUT[@]}"
echo -e "\n"

echo "📡 Checking KVM status..."
curl -X GET "${BASE_URL}/status" -i "${TIMEOUT[@]}"
echo -e "\n"

echo "🖼️  Capturing snapshot..."
curl -X GET "${BASE_URL}/snapshot" -o snapshot.png -i "${TIMEOUT[@]}"
echo "Saved snapshot as snapshot.png"
echo -e "\n"

echo "🖱️  Sending mouse event (x=5, y=100)..."
curl -X POST "${BASE_URL}/sendmouse?xCoordinate=5&yCoordinate=100" "${HEADERS[@]}" -d '{}' -i "${TIMEOUT[@]}"
echo -e "\n"

echo "🔌 Disconnecting from KVM..."
curl -X POST "${BASE_URL}/disconnect" "${HEADERS[@]}" -d '{}' -i "${TIMEOUT[@]}"
echo -e "\n"

echo "✅ All API checks complete."
