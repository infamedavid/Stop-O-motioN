bl_info = {
    "name": "StopOMotion",
    "author": "infamedavid",
    "version": (1, 6),
    "blender": (4, 0, 0),
    "location": "Dope Sheet > Sidebar > Stop-O-motion",
    "description": "Quantize selected keyframes, manage interpolation, and F-Curve modifiers (Stepped, Noise).", # Descripción ligeramente actualizada
    "category": "Animation",
}

import bpy
import math


def get_channel_type(data_path):
    """Determina si el data_path corresponde a Loc, Rot, o Scl."""
    dp_lower = data_path.lower()
    if "location" in dp_lower:
        return "LOC"
    elif "rotation_euler" in dp_lower or \
         "rotation_quaternion" in dp_lower or \
         "rotation_axis_angle" in dp_lower:
        return "ROT"
    elif "scale" in dp_lower:
        return "SCL"
    return None


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
        
        if hasattr(context, 'area') and context.area:
            context.area.tag_redraw()
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
                    
                    exists = any(abs(kp_existing.co[0] - frame) < 0.001 for kp_existing in fc.keyframe_points)
                    if not exists:
                        value = fc.evaluate(frame)
                        fc.keyframe_points.insert(frame, value, options={'FAST'})
                        inserted += 1
                    frame += self.interval

        if inserted == 0:
            self.report({'INFO'}, "No intermediate frames to insert.")
        else:
            self.report({'INFO'}, f"{inserted} keyframes inserted.")
        
        if hasattr(context, 'area') and context.area:
            context.area.tag_redraw()
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
        modified_count = 0
        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                if kp.select_control_point:
                    if kp.interpolation != 'CONSTANT':
                        kp.interpolation = 'CONSTANT'
                        modified_count +=1
        
        if modified_count > 0:
             self.report({'INFO'}, f"Set {modified_count} keyframes to CONSTANT.")
        else:
            self.report({'INFO'}, "No keyframes changed (already CONSTANT or none selected).")

        if hasattr(context, 'area') and context.area:
            context.area.tag_redraw()
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
        modified_count = 0
        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                target_kp = False
                if any_selected:
                    if kp.select_control_point:
                        target_kp = True
                else:
                    target_kp = True
                
                if target_kp:
                    if kp.interpolation != 'BEZIER':
                        kp.interpolation = 'BEZIER'
                        modified_count +=1
        
        if modified_count > 0:
            self.report({'INFO'}, f"Set {modified_count} keyframes to BEZIER.")
        else:
            self.report({'INFO'}, "No keyframes changed (already BEZIER or criteria not met).")
        
        if hasattr(context, 'area') and context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

class SMQ_OT_AddSteppedFCurveModifier(bpy.types.Operator):
    bl_idname = "smq.add_fcurve_stepped_modifier"
    bl_label = "Add Stepped Modifier to F-Curves"
    bl_description = "Add STEPPED modifier to selected keyframes' F-Curves using current panel settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        scene = context.scene

        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No animation data on the active object")
            return {'CANCELLED'}

        if scene.smq_quant_mode == 'TWOS':
            frame_step_value = 2
        elif scene.smq_quant_mode == 'THREES':
            frame_step_value = 3
        else: 
            frame_step_value = 2 
            self.report({'WARNING'}, "Unknown quantization mode for step, defaulting to 2.")

        action = obj.animation_data.action
        added = 0 

        for fc in action.fcurves:
            if any(kp.select_control_point for kp in fc.keyframe_points):
                if any(mod.type == 'STEPPED' for mod in fc.modifiers):
                    self.report({'INFO'}, f"FCurve '{fc.data_path}[{fc.array_index}]' already has a STEPPED modifier. Skipping.")
                    continue 
                mod = fc.modifiers.new(type='STEPPED')
                mod.frame_step = frame_step_value
                mod.use_influence = True 
                mod.influence = scene.smq_influence 
                mod.use_restricted_range = scene.smq_use_frame_range
                mod.frame_start = scene.smq_frame_start 
                mod.frame_end = scene.smq_frame_end                                 
                mod.blend_in = scene.smq_blend_in
                mod.blend_out = scene.smq_blend_out
                added += 1

        if added == 0:
            self.report({'WARNING'}, "No new STEPPED modifiers added. Ensure keyframes are selected and F-Curves don't already have one.")
            # return {'CANCELLED'} # Mantener el return original si lo deseas
        else:
            self.report({'INFO'}, f"{added} new STEPPED modifier(s) added with panel settings.")
        
        if hasattr(context, 'area') and context.area:
            context.area.tag_redraw()
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
        if hasattr(context, 'area') and context.area:
            context.area.tag_redraw()
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
        
        if scene.smq_quant_mode == 'TWOS':
            frame_step_value = 2
        elif scene.smq_quant_mode == 'THREES':
            frame_step_value = 3
        else: 
            frame_step_value = 2
        

        for fc in obj.animation_data.action.fcurves:
            if any(kp.select_control_point for kp in fc.keyframe_points):
                for mod in fc.modifiers:
                    if mod.type == 'STEPPED':
                        mod.frame_step = frame_step_value # <<< AÑADIDO >>>
                        mod.use_restricted_range = scene.smq_use_frame_range
                        mod.frame_start = scene.smq_frame_start
                        mod.frame_end = scene.smq_frame_end
                        mod.blend_in = scene.smq_blend_in
                        mod.blend_out = scene.smq_blend_out
                        mod.influence = scene.smq_influence
                        updated += 1
                        break # Asume un solo modificador STEPPED gestionado por el addon

        if updated == 0:
            self.report({'WARNING'}, "No STEPPED modifiers found on selected F-Curves to update. Add one first.")
            # return {'CANCELLED'} # Mantener el return original si lo deseas
        else:
            self.report({'INFO'}, f"{updated} STEPPED modifier(s) updated.")

        if hasattr(context, 'area') and context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

class SMQ_PT_Panel(bpy.types.Panel):
    bl_label = "Stop - O - Motionizer"
    bl_space_type = 'DOPESHEET_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Stop-O-motion"

    def draw(self, context):
        layout = self.layout
        scene = context.scene # Definir scene para usarla consistentemente

        layout.label(text="Quantize")
        layout.prop(scene, "smq_duplicate", text="Duplicate Action")

        row = layout.row(align=True)
        row.prop(scene, "smq_quant_mode", expand=True)

        if scene.smq_quant_mode == 'TWOS':
            op = layout.operator(SMQ_OT_QuantizeKeyframes.bl_idname, text="Apply On Twos")
            op.interval = 2
            op.duplicate = scene.smq_duplicate
        elif scene.smq_quant_mode == 'THREES':
            op = layout.operator(SMQ_OT_QuantizeKeyframes.bl_idname, text="Apply On Threes")
            op.interval = 3
            op.duplicate = scene.smq_duplicate

        layout.separator()
        layout.label(text="Fill Spaces")

        if scene.smq_quant_mode == 'TWOS':
            op = layout.operator(SMQ_OT_FillSpaces.bl_idname, text="Fill Spaces (On Twos)")
            op.interval = 2
        elif scene.smq_quant_mode == 'THREES':
            op = layout.operator(SMQ_OT_FillSpaces.bl_idname, text="Fill Spaces (On Threes)")
            op.interval = 3

        layout.separator()
        layout.label(text="Stepped Interpolation") # En tu código original es "Stepped Interpolation"

        row = layout.row(align=True)
        row.operator(SMQ_OT_SetConstantInterpolation.bl_idname, text="Curves") # "Curves" en tu original
        row.operator(SMQ_OT_RevertToBezierInterpolation.bl_idname, text="Revert")

        row = layout.row(align=True) # Esta fila es para los modificadores Stepped
        row.operator(SMQ_OT_AddSteppedFCurveModifier.bl_idname, text="As Modifier")
        row.operator(SMQ_OT_RemoveSteppedFCurveModifiers.bl_idname, text="Remove Modifier")

        layout.separator()
        layout.label(text="Stepped Modifier Settings")
        layout.prop(scene, "smq_use_frame_range")

        sub_layout_stepped = layout.column(align=True) # Para que se active/desactive con el checkbox
        sub_layout_stepped.enabled = scene.smq_use_frame_range
        row = sub_layout_stepped.row(align=True)
        row.prop(scene, "smq_frame_start")
        row.prop(scene, "smq_frame_end")

        row = sub_layout_stepped.row(align=True)
        row.prop(scene, "smq_blend_in")
        row.prop(scene, "smq_blend_out")

        layout.prop(scene, "smq_influence") # Influence para Stepped
        layout.operator("smq.update_stepped_modifier", text="Update Modifier")
        
        layout.separator()
        layout.label(text="Noise")

        row = layout.row(align=True)
        row.operator("smq.add_noise_modifier", text="As Modifier")
        row.operator("smq.remove_noise_modifier", text="Remove Modifier")

        # >>> NUEVA FILA PARA TOGGLES LOC/ROT/SCL <<<
        row = layout.row(align=True)
        row.prop(scene, "smq_noise_apply_loc", text="Loc", toggle=False) # toggle=False para checkbox estándar
        row.prop(scene, "smq_noise_apply_rot", text="Rot", toggle=False)
        row.prop(scene, "smq_noise_apply_scl", text="Scl", toggle=False)
        # <<< FIN NUEVA FILA >>>

        layout.prop(scene, "smq_noise_scale")
        layout.prop(scene, "smq_noise_strength")
        layout.prop(scene, "smq_noise_depth")

        layout.prop(scene, "smq_noise_use_frame_range") # Esta es la propiedad correcta para el frame range de noise

        sub_layout_noise = layout.column(align=True) # Para que se active/desactive con el checkbox
        sub_layout_noise.enabled = scene.smq_noise_use_frame_range # Usar la propiedad correcta
        row = sub_layout_noise.row(align=True)
        row.prop(scene, "smq_noise_frame_start") # Usar la propiedad correcta
        row.prop(scene, "smq_noise_frame_end")   # Usar la propiedad correcta

        row = sub_layout_noise.row(align=True)
        row.prop(scene, "smq_noise_blend_in")  # Usar la propiedad correcta
        row.prop(scene, "smq_noise_blend_out") # Usar la propiedad correcta

        layout.prop(scene, "smq_noise_influence") # Usar la propiedad correcta
        layout.operator("smq.update_noise_modifier", text="Update/Sync Noise") # Texto actualizado para el botón


class SMQ_OT_AddNoiseModifier(bpy.types.Operator):
    bl_idname = "smq.add_noise_modifier"
    bl_label = "Add Noise Modifier"
    bl_description = "Add NOISE modifier to F-Curves matching active Loc/Rot/Scl toggles" # Descripción actualizada
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        scene = context.scene

        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No animation data found.")
            return {'CANCELLED'}

        added = 0
        action = obj.animation_data.action # Definir action

        for fc in action.fcurves: # Usar action.fcurves
            # >>> LÓGICA MODIFICADA PARA USAR TOGGLES <<<
            if not any(kp.select_control_point for kp in fc.keyframe_points):
                continue

            channel_type = get_channel_type(fc.data_path)
            apply_modifier_to_this_channel = False

            if channel_type == "LOC" and scene.smq_noise_apply_loc:
                apply_modifier_to_this_channel = True
            elif channel_type == "ROT" and scene.smq_noise_apply_rot:
                apply_modifier_to_this_channel = True
            elif channel_type == "SCL" and scene.smq_noise_apply_scl:
                apply_modifier_to_this_channel = True
            
            if apply_modifier_to_this_channel:
                if any(mod.type == 'NOISE' for mod in fc.modifiers): # Mantener la comprobación original
                    continue
                mod = fc.modifiers.new(type='NOISE')
                mod.scale = scene.smq_noise_scale
                mod.strength = scene.smq_noise_strength
                mod.depth = scene.smq_noise_depth
                mod.use_influence = True
                mod.influence = scene.smq_noise_influence # Usar la propiedad correcta de influencia de ruido
                mod.use_restricted_range = scene.smq_noise_use_frame_range # Usar la propiedad correcta
                mod.frame_start = scene.smq_noise_frame_start # Usar la propiedad correcta
                mod.frame_end = scene.smq_noise_frame_end     # Usar la propiedad correcta
                mod.blend_in = scene.smq_noise_blend_in       # Usar la propiedad correcta
                mod.blend_out = scene.smq_noise_blend_out     # Usar la propiedad correcta
                added += 1
            # <<< FIN LÓGICA MODIFICADA >>>
        
        if added == 0:
            self.report({'INFO'}, "No new NOISE modifiers added (check selection, toggles, or if they already exist).")
        else:
            self.report({'INFO'}, f"{added} new NOISE modifier(s) added.")

        if hasattr(context, 'area') and context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

class SMQ_OT_RemoveNoiseModifier(bpy.types.Operator):
    bl_idname = "smq.remove_noise_modifier"
    bl_label = "Remove Noise Modifier"
    bl_description = "Remove ALL Noise modifiers from F-Curves with selected keyframes" # Descripción más clara
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No animation data found.")
            return {'CANCELLED'}

        removed = 0
        action = obj.animation_data.action # Definir action

        for fc in action.fcurves: # Usar action.fcurves
            if any(kp.select_control_point for kp in fc.keyframe_points):
                for mod in fc.modifiers[:]: # Iterar sobre una copia
                    if mod.type == 'NOISE':
                        fc.modifiers.remove(mod)
                        removed += 1
        
        if removed > 0:
            self.report({'INFO'}, f"{removed} NOISE modifier(s) removed.")
        else:
            self.report({'INFO'}, "No NOISE modifiers found on selected F-Curves to remove.")

        if hasattr(context, 'area') and context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

class SMQ_OT_UpdateNoiseModifier(bpy.types.Operator):
    bl_idname = "smq.update_noise_modifier"
    bl_label = "Update/Sync Noise Modifiers" # Etiqueta actualizada
    bl_description = ("Synchronizes NOISE modifiers based on Loc/Rot/Scl toggles: "
                      "Adds if missing & toggle active, updates if present & toggle active, "
                      "removes if present & toggle inactive.") # Descripción actualizada
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        scene = context.scene
        
        if not obj or not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "No animation data on active object.")
            return {'CANCELLED'}

        action = obj.animation_data.action
        updated_count = 0
        added_count = 0
        removed_count = 0

        for fc in action.fcurves:
            if not any(kp.select_control_point for kp in fc.keyframe_points):
                continue

            channel_type = get_channel_type(fc.data_path)
            is_toggle_active_for_channel = False

            if channel_type == "LOC" and scene.smq_noise_apply_loc:
                is_toggle_active_for_channel = True
            elif channel_type == "ROT" and scene.smq_noise_apply_rot:
                is_toggle_active_for_channel = True
            elif channel_type == "SCL" and scene.smq_noise_apply_scl:
                is_toggle_active_for_channel = True
            
            existing_noise_mod = None
            for mod_iter in fc.modifiers:
                if mod_iter.type == 'NOISE':
                    existing_noise_mod = mod_iter
                    break
            
            if is_toggle_active_for_channel:
                if existing_noise_mod:
                    # Actualizar existente
                    existing_noise_mod.scale = scene.smq_noise_scale
                    existing_noise_mod.strength = scene.smq_noise_strength
                    existing_noise_mod.depth = scene.smq_noise_depth
                    existing_noise_mod.use_restricted_range = scene.smq_noise_use_frame_range
                    existing_noise_mod.frame_start = scene.smq_noise_frame_start
                    existing_noise_mod.frame_end = scene.smq_noise_frame_end
                    existing_noise_mod.blend_in = scene.smq_noise_blend_in
                    existing_noise_mod.blend_out = scene.smq_noise_blend_out
                    existing_noise_mod.influence = scene.smq_noise_influence
                    updated_count += 1
                else:
                    # Añadir nuevo
                    mod = fc.modifiers.new(type='NOISE')
                    mod.scale = scene.smq_noise_scale
                    mod.strength = scene.smq_noise_strength
                    mod.depth = scene.smq_noise_depth
                    mod.use_influence = True # Importante para que la influencia funcione
                    mod.influence = scene.smq_noise_influence
                    mod.use_restricted_range = scene.smq_noise_use_frame_range
                    mod.frame_start = scene.smq_noise_frame_start
                    mod.frame_end = scene.smq_noise_frame_end
                    mod.blend_in = scene.smq_noise_blend_in
                    mod.blend_out = scene.smq_noise_blend_out
                    added_count += 1
            else: # Toggle está inactivo para este canal
                if existing_noise_mod:
                    # Remover existente
                    fc.modifiers.remove(existing_noise_mod)
                    removed_count += 1
        
        report_parts = []
        if added_count > 0:
            report_parts.append(f"{added_count} added")
        if updated_count > 0:
            report_parts.append(f"{updated_count} updated")
        if removed_count > 0:
            report_parts.append(f"{removed_count} removed")

        if not report_parts:
            self.report({'INFO'}, "No NOISE modifiers changed (check selection and Loc/Rot/Scl toggles).")
        else:
            self.report({'INFO'}, f"Noise modifiers: {', '.join(report_parts)}.")

        if hasattr(context, 'area') and context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


classes = [
    SMQ_OT_QuantizeKeyframes,
    SMQ_OT_FillSpaces,
    SMQ_OT_SetConstantInterpolation,
    SMQ_OT_RevertToBezierInterpolation,
    SMQ_OT_AddSteppedFCurveModifier,
    SMQ_OT_RemoveSteppedFCurveModifiers,
    SMQ_OT_UpdateSteppedModifier,
    SMQ_PT_Panel,
    SMQ_OT_AddNoiseModifier,
    SMQ_OT_RemoveNoiseModifier,
    SMQ_OT_UpdateNoiseModifier,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.smq_duplicate = bpy.props.BoolProperty(
        name="Duplicate Action",
        description="Duplicate current action before quantizing",
        default=True
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

    # Propiedades para Stepped Modifier (originales)
    bpy.types.Scene.smq_use_frame_range = bpy.props.BoolProperty(name="Frame Range (Stepped)", default=False, description="Restrict Stepped modifier effect to a frame range") # Nombre único
    bpy.types.Scene.smq_frame_start = bpy.props.IntProperty(name="Start (Stepped)", default=1, min=0) # Nombre único
    bpy.types.Scene.smq_frame_end = bpy.props.IntProperty(name="End (Stepped)", default=250, min=0) # Nombre único
    bpy.types.Scene.smq_blend_in = bpy.props.IntProperty(name="Blend In (Stepped)", default=0, min=0) # Nombre único
    bpy.types.Scene.smq_blend_out = bpy.props.IntProperty(name="Blend Out (Stepped)", default=0, min=0) # Nombre único
    bpy.types.Scene.smq_influence = bpy.props.FloatProperty(name="Influence (Stepped)", default=1.0, min=0.0, max=1.0) # Nombre único

    # >>> NUEVAS PROPIEDADES PARA NOISE TOGGLES <<<
    bpy.types.Scene.smq_noise_apply_loc = bpy.props.BoolProperty(
        name="Loc",
        description="Target Location channels for Noise operations",
        default=False
    )
    bpy.types.Scene.smq_noise_apply_rot = bpy.props.BoolProperty(
        name="Rot",
        description="Target Rotation channels for Noise operations",
        default=True # Por defecto Rotación activado
    )
    bpy.types.Scene.smq_noise_apply_scl = bpy.props.BoolProperty(
        name="Scl",
        description="Target Scale channels for Noise operations",
        default=False
    )
    # <<< FIN NUEVAS PROPIEDADES >>>

    # Propiedades para Noise Modifier (originales, pero con nombres únicos para evitar conflictos si fueran diferentes)
    # Tu código original usa los mismos nombres para las propiedades de Stepped y Noise (ej. smq_influence).
    # Esto significa que comparten el mismo valor. Si quieres que sean independientes, necesitas nombres diferentes.
    # Voy a asumir que quieres que sean independientes para Noise, así que les añadiré un sufijo "_noise".
    # Si quieres que compartan valor, elimina el sufijo "_noise" y ajusta el panel.

    bpy.types.Scene.smq_noise_scale = bpy.props.FloatProperty(name="Scale (Noise)", default=20.0, min=0.01, max=200.0)
    bpy.types.Scene.smq_noise_strength = bpy.props.FloatProperty(name="Strength (Noise)", default=0.007, min=0.0, max=10.0) # Permitir 0 para desactivar temporalmente
    bpy.types.Scene.smq_noise_depth = bpy.props.IntProperty(name="Detail (Noise)", default=2, min=0, max=10) # 'Depth' en Blender es 'Detail' para Noise

    bpy.types.Scene.smq_noise_use_frame_range = bpy.props.BoolProperty(name="Frame Range (Noise)", default=False, description="Restrict Noise modifier effect to a frame range")
    bpy.types.Scene.smq_noise_frame_start = bpy.props.IntProperty(name="Start (Noise)", default=1, min=0)
    bpy.types.Scene.smq_noise_frame_end = bpy.props.IntProperty(name="End (Noise)", default=250, min=0)
    bpy.types.Scene.smq_noise_blend_in = bpy.props.IntProperty(name="Blend In (Noise)", default=0, min=0)
    bpy.types.Scene.smq_noise_blend_out = bpy.props.IntProperty(name="Blend Out (Noise)", default=0, min=0)
    bpy.types.Scene.smq_noise_influence = bpy.props.FloatProperty(name="Influence (Noise)", default=1.0, min=0.0, max=1.0)

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError: pass # Ignorar si no estaba registrada

    props_to_delete = [
        "smq_duplicate", "smq_quant_mode",
        "smq_use_frame_range", "smq_frame_start", "smq_frame_end",
        "smq_blend_in", "smq_blend_out", "smq_influence",
        # >>> NUEVAS PROPIEDADES A ELIMINAR <<<
        "smq_noise_apply_loc", "smq_noise_apply_rot", "smq_noise_apply_scl",
        # <<< FIN NUEVAS PROPIEDADES >>>
        "smq_noise_scale", "smq_noise_strength", "smq_noise_depth",
        "smq_noise_use_frame_range", "smq_noise_frame_start", "smq_noise_frame_end",
        "smq_noise_blend_in", "smq_noise_blend_out", "smq_noise_influence"
    ]
    for prop_name in props_to_delete:
        if hasattr(bpy.types.Scene, prop_name):
            try:
                delattr(bpy.types.Scene, prop_name)
            except AttributeError: pass # Ignorar si ya fue eliminada o no existía

if __name__ == "__main__":
    # Para pruebas, es útil desregistrar primero si el addon ya está cargado
    # Esto puede requerir manejo de errores si no está registrado.
    try:
        unregister()
    except Exception as e:
        print(f"Error unregistering: {e}") # Para depuración
        pass
    register()