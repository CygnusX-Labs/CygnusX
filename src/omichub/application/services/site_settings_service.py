"""站点设置应用服务 — 单行配置的读取与更新"""

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.site_settings import SiteSettingsDTO, TOTPPolicy, UpdateSiteSettingsDTO
from omichub.infrastructure.database.models.site_settings import SiteSettingModel


class SiteSettingsService:
    """站点设置服务"""

    _SINGLETON_ID = 1

    def __init__(self, db: AsyncSession):
        self._db = db

    async def _get_or_create(self) -> SiteSettingModel:
        model = await self._db.get(SiteSettingModel, self._SINGLETON_ID)
        if model is None:
            model = SiteSettingModel(id=self._SINGLETON_ID, registration_enabled=True, totp_policy="optional")
            self._db.add(model)
            await self._db.flush()
        return model

    async def get_settings(self) -> SiteSettingsDTO:
        model = await self._get_or_create()
        return SiteSettingsDTO(
            registration_enabled=model.registration_enabled,
            totp_policy=model.totp_policy,
        )

    async def is_registration_enabled(self) -> bool:
        model = await self._get_or_create()
        return model.registration_enabled

    async def get_totp_policy(self) -> TOTPPolicy:
        model = await self._get_or_create()
        policy = model.totp_policy
        if policy not in ("off", "optional", "required"):
            return "optional"
        return policy

    async def update_settings(self, req: UpdateSiteSettingsDTO) -> SiteSettingsDTO:
        model = await self._get_or_create()
        if req.registration_enabled is not None:
            model.registration_enabled = req.registration_enabled
        if req.totp_policy is not None:
            model.totp_policy = req.totp_policy
        await self._db.flush()
        return await self.get_settings()
