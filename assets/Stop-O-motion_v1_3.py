bl_info = {
    "name": "Stop-O-motion",
    "author": "infamedavid",
    "version": (1, 3),
    "blender": (4, 0, 0),
    "location": "Dope Sheet > Sidebar > Stop-O-motion",
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
    bl_description = "Add STEPPED modifier to selected keyframes' F-Curves using current panel settings" # Descripción actualizada
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object # O context.active_object para consistencia
        scene = context.scene # Necesitamos acceso a las propiedades de la escena

        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No animation data on the active object")
            return {'CANCELLED'}

        # Determinar el frame_step basado en el modo de cuantización
        if scene.smq_quant_mode == 'TWOS':
            frame_step_value = 2
        elif scene.smq_quant_mode == 'THREES':
            frame_step_value = 3
        else: # Por si acaso se añaden más modos o hay un default inesperado
            frame_step_value = 2 
            self.report({'WARNING'}, "Unknown quantization mode for step, defaulting to 2.")

        action = obj.animation_data.action
        added = 0 

        for fc in action.fcurves:
            if any(kp.select_control_point for kp in fc.keyframe_points):
                # Comprobar si ya existe un modificador STEPPED
                if any(mod.type == 'STEPPED' for mod in fc.modifiers):
                    self.report({'INFO'}, f"FCurve '{fc.data_path}[{fc.array_index}]' already has a STEPPED modifier. Skipping.")
                    continue # Saltar esta F-Curve y continuar con la siguiente

                mod = fc.modifiers.new(type='STEPPED')

                # Configurar el modificador con los valores del panel
                mod.frame_step = frame_step_value
                
                mod.use_influence = True # Solicitud anterior
                mod.influence = scene.smq_influence # Inicializar con el valor del panel

                mod.use_restricted_range = scene.smq_use_frame_range

                mod.frame_start = scene.smq_frame_start # Inicializar con el valor del panel
                mod.frame_end = scene.smq_frame_end   # Inicializar con el valor del panel
                
                # También inicializar blend_in y blend_out
                # (Asegúrate de que smq_blend_in y smq_blend_out sean FloatProperty si no lo son ya)
                mod.blend_in = scene.smq_blend_in
                mod.blend_out = scene.smq_blend_out
                
                added += 1

        if added == 0:
            self.report({'WARNING'}, "No new STEPPED modifiers added. Ensure keyframes are selected and F-Curves don't already have one.")
            return {'CANCELLED'}
        
        self.report({'INFO'}, f"{added} new STEPPED modifier(s) added with panel settings.")
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

class SMQ_OT_UpdateSteppedModifier(bpy.types.Operator):
    bl_idname = "smq.update_stepped_modifier"
    bl_label = "Update Stepped Modifier"
    bl_description = "Update parameters of the STEPPED F-Curve modifier"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        obj = context.object

        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No animation data on the active object")
            return {'CANCELLED'}

        updated = 0

        for fc in obj.animation_data.action.fcurves:
            if any(kp.select_control_point for kp in fc.keyframe_points):
                for mod in fc.modifiers:
                    if mod.type == 'STEPPED':
                        mod.use_restricted_range = scene.smq_use_frame_range
                        mod.frame_start = scene.smq_frame_start
                        mod.frame_end = scene.smq_frame_end
                        mod.blend_in = scene.smq_blend_in
                        mod.blend_out = scene.smq_blend_out
                        mod.influence = scene.smq_influence
                        updated += 1
                        break

        if updated == 0:
            self.report({'WARNING'}, "Add the STEPPED modifier first.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"{updated} modifier(s) updated.")
        return {'FINISHED'}

class SMQ_PT_Panel(bpy.types.Panel):
    bl_label = "Stop - O - Motionizer"
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Stop-O-motion"

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

        layout.separator()
        layout.label(text="Stepped Modifier Settings")
        layout.prop(context.scene, "smq_use_frame_range")

        row = layout.row(align=True)
        row.prop(context.scene, "smq_frame_start")
        row.prop(context.scene, "smq_frame_end")

        row = layout.row(align=True)
        row.prop(context.scene, "smq_blend_in")
        row.prop(context.scene, "smq_blend_out")

        layout.prop(context.scene, "smq_influence")
        layout.operator("smq.update_stepped_modifier", text="Update Modifier")

classes = [
    SMQ_OT_QuantizeKeyframes,
    SMQ_OT_FillSpaces,
    SMQ_OT_SetConstantInterpolation,
    SMQ_OT_RevertToBezierInterpolation,
    SMQ_OT_AddSteppedFCurveModifier,
    SMQ_OT_RemoveSteppedFCurveModifiers,
    SMQ_OT_UpdateSteppedModifier,
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

    bpy.types.Scene.smq_use_frame_range = bpy.props.BoolProperty(name="Frame Range", default=False)
    bpy.types.Scene.smq_frame_start = bpy.props.IntProperty(name="Start", default=1)
    bpy.types.Scene.smq_frame_end = bpy.props.IntProperty(name="End", default=250)
    bpy.types.Scene.smq_blend_in = bpy.props.IntProperty(name="Blend In", default=0)
    bpy.types.Scene.smq_blend_out = bpy.props.IntProperty(name="Blend Out", default=0)
    bpy.types.Scene.smq_influence = bpy.props.FloatProperty(name="Influence", default=1.0, min=0.0, max=1.0)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.smq_duplicate
    del bpy.types.Scene.smq_quant_mode
    del bpy.types.Scene.smq_use_frame_range
    del bpy.types.Scene.smq_frame_start
    del bpy.types.Scene.smq_frame_end
    del bpy.types.Scene.smq_blend_in
    del bpy.types.Scene.smq_blend_out
    del bpy.types.Scene.smq_influence

if __name__ == "__main__":
    register()
