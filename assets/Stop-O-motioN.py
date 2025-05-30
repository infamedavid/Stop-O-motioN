bl_info = {
    "name": "Stop Motion Quantizer",
    "author": "infame",
    "version": (1, 0),
    "blender": (4, 0, 0),
    "location": "Dope Sheet > Sidebar > Stop Motion",
    "description": "Quantize selected keyframes to on twos, threes, etc.",
    "category": "Animation",
}

import bpy
import math

class SMQ_OT_QuantizeKeyframes(bpy.types.Operator):
    bl_idname = "smq.quantize_keyframes"
    bl_label = "Quantize Keyframes"
    bl_description = "Move selected keyframes to fall on multiples of N preserving timing"
    bl_options = {"REGISTER", "UNDO"}

    interval: bpy.props.IntProperty()
    duplicate: bpy.props.BoolProperty()

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No active object with animation data.")
            return {'CANCELLED'}

        action = obj.animation_data.action

        if self.duplicate:
            new_action = action.copy()
            action.use_fake_user = True
            new_action.name = action.name + "_quantized"
            obj.animation_data.action = new_action
            action = new_action

        fcurves = action.fcurves
        fcurve_map = {}

        for fc in fcurves:
            selected = [kp for kp in fc.keyframe_points if kp.select_control_point]
            if selected:
                fcurve_map[fc] = sorted(selected, key=lambda kp: kp.co[0])

        if not fcurve_map:
            self.report({'WARNING'}, "No selected keyframes found.")
            return {'CANCELLED'}

        for fc, keyframes in fcurve_map.items():
            if not keyframes:
                continue

            ref_frame = keyframes[0].co[0]
            keyframes[0].select_control_point = False
            keyframes[0].co[0] = ref_frame

            quantized_frames = {round(ref_frame)}
            prev_frame = ref_frame

            for kp in keyframes[1:]:
                delta = kp.co[0] - prev_frame
                quantized_delta = round(delta / self.interval) * self.interval
                new_frame = round(prev_frame + quantized_delta)

                while new_frame in quantized_frames:
                    new_frame += self.interval

                quantized_frames.add(new_frame)
                kp.co[0] = new_frame
                prev_frame = new_frame
                kp.select_control_point = False

        return {'FINISHED'}

class SMQ_OT_FillSpaces(bpy.types.Operator):
    bl_idname = "smq.fill_spaces"
    bl_label = "Fill Spaces"
    bl_description = "Add keyframes in between selected keyframes using current quantization interval"
    bl_options = {"REGISTER", "UNDO"}

    interval: bpy.props.IntProperty()

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No active object with animation data.")
            return {'CANCELLED'}

        action = obj.animation_data.action
        fcurves = action.fcurves
        inserted = 0

        for fc in fcurves:
            keyframes = [kp.co[0] for kp in fc.keyframe_points if kp.select_control_point]
            if len(keyframes) < 2:
                continue

            keyframes = sorted(set(round(k) for k in keyframes))

            for i in range(len(keyframes) - 1):
                start = keyframes[i]
                end = keyframes[i + 1]
                frame = start + self.interval
                while frame < end:
                    value = fc.evaluate(frame)
                    fc.keyframe_points.insert(frame, value, options={'FAST'})
                    inserted += 1
                    frame += self.interval

        if inserted == 0:
            self.report({'INFO'}, "No intermediate frames to insert.")
        else:
            self.report({'INFO'}, f"{inserted} keyframes inserted.")
        return {'FINISHED'}

class SMQ_OT_SetConstantInterpolation(bpy.types.Operator):
    bl_idname = "smq.set_constant_interpolation"
    bl_label = "Set Constant Interpolation"
    bl_description = "Set interpolation to CONSTANT for selected keyframes"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No animation data found.")
            return {'CANCELLED'}

        action = obj.animation_data.action

        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                if kp.select_control_point:
                    kp.interpolation = 'CONSTANT'

        return {'FINISHED'}

class SMQ_OT_RevertToBezierInterpolation(bpy.types.Operator):
    bl_idname = "smq.revert_to_bezier"
    bl_label = "Revert to Bezier"
    bl_description = "Set interpolation to BEZIER for selected keyframes or all if none selected"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No animation data found.")
            return {'CANCELLED'}

        action = obj.animation_data.action
        any_selected = any(
            kp.select_control_point for fc in action.fcurves for kp in fc.keyframe_points
        )

        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                if any_selected:
                    if kp.select_control_point:
                        kp.interpolation = 'BEZIER'
                else:
                    kp.interpolation = 'BEZIER'

        return {'FINISHED'}

class SMQ_OT_AddSteppedFCurveModifier(bpy.types.Operator):
    bl_idname = "smq.add_fcurve_stepped_modifier"
    bl_label = "Add Stepped Modifier to F-Curves"
    bl_description = "Add STEPPED modifier to selected keyframes' F-Curves"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No animation data on the active object")
            return {'CANCELLED'}

        frame_step_value = 2 if context.scene.smq_quant_mode == 'TWOS' else 3
        action = obj.animation_data.action
        added = 0 

        for fc in action.fcurves:

            if any(kp.select_control_point for kp in fc.keyframe_points):

                if any(mod.type == 'STEPPED' for mod in fc.modifiers):
                    self.report({'WARNING'}, "Remove previous first")

                    return {'CANCELLED'}

                mod = fc.modifiers.new(type='STEPPED')
                mod.frame_step = frame_step_value
                added += 1


        if added == 0:
            self.report({'WARNING'}, "No selected keyframes found in F-Curves")
            return {'CANCELLED'}

        return {'FINISHED'}

class SMQ_OT_RemoveSteppedFCurveModifiers(bpy.types.Operator):
    bl_idname = "smq.remove_fcurve_stepped_modifiers"
    bl_label = "Remove Stepped Modifiers"
    bl_description = "Remove all STEPPED modifiers from selected F-Curves"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No animation data on the active object")
            return {'CANCELLED'}

        action = obj.animation_data.action
        removed = 0
        for fc in action.fcurves:
            if any(kp.select_control_point for kp in fc.keyframe_points):
                for mod in fc.modifiers[:]:
                    if mod.type == 'STEPPED':
                        fc.modifiers.remove(mod)
                        removed += 1

        self.report({'INFO'}, f"{removed} STEPPED modifiers removed.")
        return {'FINISHED'}

class SMQ_PT_Panel(bpy.types.Panel):
    bl_label = "Stop Motionizer"
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Stop Motion"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Quantize")
        layout.prop(context.scene, "smq_duplicate", text="Duplicate Action")

        row = layout.row(align=True)
        row.prop(context.scene, "smq_quant_mode", expand=True)

        if context.scene.smq_quant_mode == 'TWOS':
            op = layout.operator(SMQ_OT_QuantizeKeyframes.bl_idname, text="Apply On Twos")
            op.interval = 2
            op.duplicate = context.scene.smq_duplicate
        elif context.scene.smq_quant_mode == 'THREES':
            op = layout.operator(SMQ_OT_QuantizeKeyframes.bl_idname, text="Apply On Threes")
            op.interval = 3
            op.duplicate = context.scene.smq_duplicate

        layout.separator()
        layout.label(text="Fill Spaces")

        if context.scene.smq_quant_mode == 'TWOS':
            op = layout.operator(SMQ_OT_FillSpaces.bl_idname, text="Fill Spaces (On Twos)")
            op.interval = 2
        elif context.scene.smq_quant_mode == 'THREES':
            op = layout.operator(SMQ_OT_FillSpaces.bl_idname, text="Fill Spaces (On Threes)")
            op.interval = 3

        layout.separator()
        layout.label(text="Stepped Interpolation")

        row = layout.row(align=True)
        row.operator(SMQ_OT_SetConstantInterpolation.bl_idname, text="Curves")
        row.operator(SMQ_OT_RevertToBezierInterpolation.bl_idname, text="Revert")

        row = layout.row(align=True)
        row.operator(SMQ_OT_AddSteppedFCurveModifier.bl_idname, text="As Modifier")
        row.operator(SMQ_OT_RemoveSteppedFCurveModifiers.bl_idname, text="Remove Modifier")

classes = [
    SMQ_OT_QuantizeKeyframes,
    SMQ_OT_FillSpaces,
    SMQ_OT_SetConstantInterpolation,
    SMQ_OT_RevertToBezierInterpolation,
    SMQ_OT_AddSteppedFCurveModifier,
    SMQ_OT_RemoveSteppedFCurveModifiers,
    SMQ_PT_Panel,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.smq_duplicate = bpy.props.BoolProperty(
        name="Duplicate Action",
        description="Duplicate current action before quantizing",
        default=False
    )

    bpy.types.Scene.smq_quant_mode = bpy.props.EnumProperty(
        name="Quantization Mode",
        description="Choose quantization interval",
        items=[
            ('TWOS', 'On Twos', "Quantize to every 2 frames"),
            ('THREES', 'On Threes', "Quantize to every 3 frames")
        ],
        default='TWOS'
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.smq_duplicate
    del bpy.types.Scene.smq_quant_mode

if __name__ == "__main__":
    register()
