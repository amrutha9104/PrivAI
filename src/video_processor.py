import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO
import os

class VideoProcessor:
    def __init__(self, model_path="models/downloaded_models/yolov8n.pt"):
        print("🎬 Initializing VideoProcessor...")
        self.face_detection = mp.solutions.face_detection.FaceDetection(
            model_selection=0, min_detection_confidence=0.5
        )
        self.selfie_segmentation = mp.solutions.selfie_segmentation.SelfieSegmentation(
            model_selection=1
        )
        if os.path.exists(model_path):
            self.yolo_model = YOLO(model_path)
            print(f"✅ YOLO loaded: {model_path}")
        else:
            print(f"⚠️ YOLO not found at {model_path}")
            self.yolo_model = None
        
        self.sensitive_classes = [24, 25, 26, 62, 63, 64, 66, 67, 73, 77, 78]

    def process_frame(self, frame: np.ndarray, user_id: str, db, settings: dict) -> tuple:
        if frame is None: return frame, {}
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            processed = frame.copy().astype(np.float32)
            detections = {
                'faces_blurred': 0,
                'objects_blurred': 0,
                'object_classes': [],
                'faces': [],  # ADD: store face coordinates
                'objects': [] # ADD: store object coordinates
            }
            
            # Background processing
            bg_mode = settings.get('background_mode', 'blur')
            if bg_mode and bg_mode != 'none':
                processed = self._process_background(rgb_frame, processed, bg_mode)
            
            # Face processing (modified to return coordinates)
            if settings.get('blur_unknown_faces', True):
                processed, face_coords = self._process_faces_with_overlay(rgb_frame, processed, user_id, db)
                detections['faces_blurred'] = len(face_coords)
                detections['faces'] = face_coords
            
            # Object processing (modified to return coordinates)
            if settings.get('blur_objects', True) and self.yolo_model:
                processed, obj_coords, obj_classes = self._process_objects_with_overlay(rgb_frame, processed, settings)
                detections['objects_blurred'] = len(obj_coords)
                detections['objects'] = obj_coords
                detections['object_classes'] = obj_classes
            
            return processed.astype(np.uint8), detections
        except Exception as e:
            print(f"❌ Error: {e}")
            return frame, {}

    def _process_background(self, rgb_frame, output_frame, mode):
        try:
            results = self.selfie_segmentation.process(rgb_frame)
            if results and results.segmentation_mask is not None:
                mask = results.segmentation_mask > 0.1
                mask_3d = np.dstack([mask]*3)
                
                if mode == 'blur':
                    bg_blurred = cv2.GaussianBlur(output_frame, (55, 55), 0)
                    return np.where(mask_3d, output_frame, bg_blurred)
                elif mode == 'pixelate':
                    h, w = output_frame.shape[:2]
                    temp = cv2.resize(output_frame, (w//20, h//20))
                    bg_pixelated = cv2.resize(temp, (w, h), interpolation=cv2.NEAREST)
                    return np.where(mask_3d, output_frame, bg_pixelated)
                elif mode == 'replace':
                    bg_replaced = np.full_like(output_frame, 128)
                    return np.where(mask_3d, output_frame, bg_replaced)
            return output_frame
        except Exception as e:
            print(f"⚠️ Background error: {e}")
            return output_frame

    def _process_faces_with_overlay(self, rgb_frame, output_frame, user_id, db):
        """Process faces and return coordinates for overlay"""
        face_coords = []
        try:
            authorized_embeddings = {}
            try: authorized_embeddings = dict(db.get_all_authorized_face_embeddings())
            except: pass
            
            results = self.face_detection.process(rgb_frame)
            h, w = output_frame.shape[:2]
            
            if results and results.detections:
                for detection in results.detections:
                    bbox = detection.location_data.relative_bounding_box
                    x, y = int(bbox.xmin * w), int(bbox.ymin * h)
                    x2, y2 = min(w, x + int(bbox.width * w)), min(h, y + int(bbox.height * h))
                    
                    if x2 <= x or y2 <= y: continue
                    
                    face_crop = rgb_frame[y:y2, x:x2]
                    if face_crop.size == 0: continue
                    
                    face_embedding = face_crop.mean(axis=(0, 1))
                    is_authorized = False
                    
                    if authorized_embeddings:
                        for auth_id, auth_emb in authorized_embeddings.items():
                            norm = np.linalg.norm(face_embedding) * np.linalg.norm(auth_emb) + 1e-8
                            similarity = np.dot(face_embedding, auth_emb) / norm
                            if similarity > 0.85:
                                is_authorized = True
                                break
                    
                    # Store coordinates for overlay
                    face_coords.append({
                        'x1': x, 'y1': y, 'x2': x2, 'y2': y2,
                        'authorized': is_authorized
                    })
                    
                    # Draw green box if authorized, red if not
                    color = (0, 255, 0) if is_authorized else (0, 0, 255)
                    cv2.rectangle(processed, (x, y), (x2, y2), color, 2)
                    cv2.putText(processed, f"{'Auth' if is_authorized else 'Blocked'}", 
                               (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                    
                    if not is_authorized:
                        face_region = output_frame[y:y2, x:x2]
                        if face_region.size > 0:
                            processed[y:y2, x:x2] = cv2.GaussianBlur(face_region, (55, 55), 0)
            
            return processed, face_coords
        except Exception as e:
            print(f"❌ Face processing error: {e}")
            return output_frame, []

    def _process_objects_with_overlay(self, rgb_frame, output_frame, settings):
        """Process objects and return coordinates for overlay"""
        obj_coords = []
        obj_classes = []
        
        if not self.yolo_model:
            return output_frame, [], []
        
        try:
            results = self.yolo_model(rgb_frame, stream=True, conf=0.3)
            
            for r in results:
                for box in r.boxes:
                    cls = int(box.cls[0])
                    class_name = self.yolo_model.names[cls]
                    
                    if cls in self.sensitive_classes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        x1, y1 = max(0, x1 - 10), max(0, y1 - 10)
                        x2 = min(output_frame.shape[1], x2 + 10)
                        y2 = min(output_frame.shape[0], y2 + 10)
                        
                        obj_region = output_frame[y1:y2, x1:x2]
                        if obj_region.size > 0:
                            # Store coordinates
                            obj_coords.append({
                                'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                                'class': class_name
                            })
                            obj_classes.append(class_name)
                            
                            # Draw red box and label
                            cv2.rectangle(processed, (x1, y1), (x2, y2), (0, 165, 255), 3)
                            cv2.putText(processed, f"BLURRED: {class_name}", 
                                       (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
                            
                            processed[y1:y2, x1:x2] = cv2.GaussianBlur(obj_region, (75, 75), 0)
            
            return processed, obj_coords, obj_classes
        except Exception as e:
            print(f"❌ Object processing error: {e}")
            return output_frame, [], []