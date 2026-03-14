import cv2

aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

for marker_id in range(12):  # IDs 0–11
    marker_image = cv2.aruco.generateImageMarker(aruco_dict, marker_id, 500)
    cv2.imwrite(f"marker_{marker_id}.png", marker_image)

print("Done! 12 markers saved.")